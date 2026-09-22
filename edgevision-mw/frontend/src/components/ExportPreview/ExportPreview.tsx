import React, { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { AxiosError } from "axios";
import api from "../../services/api";
import { PageShell } from "../PageShell";
import { useStudioSettings } from "../../context/StudioSettingsContext";

interface AugmentationConfig {
  horizontal_flip: boolean;
  rotation_degrees: number;
  brightness_delta: number;
  contrast_delta: number;
  saturation_delta: number;
  mosaic: boolean;
  mixup: boolean;
}

interface PreviewImage {
  original_url: string;
  augmented_url: string;
  annotations_transformed: boolean;
  class_distribution: Record<string, number>;
}

interface ExportFormat {
  id: string;
  name: string;
  description: string;
  extension: string;
}

interface Props {
  datasetId: string;
}

const FORMATS: ExportFormat[] = [
  { id: "coco", name: "COCO JSON", description: "Standard object detection format", extension: "json" },
  { id: "yolo", name: "YOLO TXT", description: "Darknet format, one txt per image", extension: "txt" },
  { id: "pascal_voc", name: "Pascal VOC", description: "XML annotations per image", extension: "xml" },
];

const DEFAULT_AUG: AugmentationConfig = {
  horizontal_flip: false,
  rotation_degrees: 0,
  brightness_delta: 0,
  contrast_delta: 0,
  saturation_delta: 0,
  mosaic: false,
  mixup: false,
};

export const ExportPreview: React.FC<Props> = ({ datasetId }) => {
  const { t } = useTranslation();
  const { expertMode } = useStudioSettings();
  const [format, setFormat] = useState<string>("coco");
  const [augmentations, setAugmentations] = useState<AugmentationConfig>(DEFAULT_AUG);
  const [splitRatio, setSplitRatio] = useState({ train: 0.7, val: 0.2, test: 0.1 });
  const [stratify, setStratify] = useState<string[]>(["district"]);
  const [previewImages, setPreviewImages] = useState<PreviewImage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);
  const [buildJobId, setBuildJobId] = useState<string | null>(null);
  const [buildStatus, setBuildStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const generatePreview = useCallback(async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const res = await api.post("/studio/export/preview", {
        dataset_id: datasetId,
        format,
        augmentations,
        sample_size: 10,
      });
      setPreviewImages(res.data.preview_images || []);
    } catch (err: unknown) {
      console.error("Preview generation failed:", err);
      const detail = err instanceof AxiosError ? err.response?.data?.detail : undefined;
      setError(detail || "Preview failed");
    } finally {
      setIsGenerating(false);
    }
  }, [datasetId, format, augmentations]);

  const buildExport = async () => {
    setIsBuilding(true);
    setError(null);
    try {
      const res = await api.post("/studio/export/build", {
        dataset_id: datasetId,
        format,
        split_ratio: splitRatio,
        augmentations: {
          enabled: Object.values(augmentations).some((v) => v !== false && v !== 0),
          config: augmentations,
        },
        stratify,
        watermark: true,
      });
      setBuildJobId(res.data.job_id);
      setBuildStatus("PENDING");
      pollBuildStatus(res.data.job_id);
    } catch (err: unknown) {
      console.error("Export build failed:", err);
      const detail = err instanceof AxiosError ? err.response?.data?.detail : undefined;
      setError(detail || "Build failed");
      setIsBuilding(false);
    }
  };

  const pollBuildStatus = useCallback((jobId: string) => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await api.get(`/studio/exports/${jobId}`);
        setBuildStatus(res.data.status);
        if (res.data.status === "COMPLETED") {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          setIsBuilding(false);
          if (res.data.download_url) {
            window.open(res.data.download_url, "_blank");
          }
        } else if (res.data.status === "FAILED") {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          setIsBuilding(false);
          setError(res.data.error || t("export.buildFailed", "Export build failed"));
        }
      } catch {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        setIsBuilding(false);
        setError(t("export.buildFailed", "Export build failed — check connection and retry"));
      }
    }, 3000);
  }, [t]);

  const updateAug = (key: keyof AugmentationConfig, value: boolean | number) => {
    setAugmentations((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <PageShell
      accent="export"
      className="export-preview-page"
      title={t("export.title", "Dataset Export Builder")}
      badge={datasetId}
    >
      {error && <div className="export-error">{error}</div>}

      <div className="export-layout">
        <div className="export-config">
          <div className="config-section">
            <h3>{t("export.format", "Format")}</h3>
            <div className="format-options">
              {FORMATS.map((f) => (
                <label key={f.id} className={`format-option ${format === f.id ? "active" : ""}`}>
                  <input
                    type="radio"
                    name="format"
                    value={f.id}
                    checked={format === f.id}
                    onChange={(e) => setFormat(e.target.value)}
                  />
                  <div className="format-info">
                    <strong>{f.name}</strong>
                    <span>{f.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="config-section">
            <h3>{t("export.split", "Train / Val / Test Split")}</h3>
            <div className="split-sliders">
              <label>
                {t("export.train", "Train")}: {(splitRatio.train * 100).toFixed(0)}%
                <input
                  type="range"
                  min="0.5"
                  max="0.9"
                  step="0.05"
                  value={splitRatio.train}
                  aria-valuemin={0.5}
                  aria-valuemax={0.9}
                  aria-valuenow={splitRatio.train}
                  aria-label={t("export.train")}
                  onChange={(e) => {
                    const train = parseFloat(e.target.value);
                    const remaining = 1 - train;
                    setSplitRatio({
                      train,
                      val: remaining * 0.67,
                      test: remaining * 0.33,
                    });
                  }}
                />
              </label>
              <label>
                {t("export.val", "Val")}: {(splitRatio.val * 100).toFixed(0)}%
                <input
                  type="range"
                  min="0.05"
                  max="0.3"
                  step="0.05"
                  value={splitRatio.val}
                  aria-valuemin={0.05}
                  aria-valuemax={0.3}
                  aria-valuenow={splitRatio.val}
                  aria-label={t("export.val")}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    const remaining = 1 - splitRatio.train;
                    setSplitRatio((prev) => ({
                      ...prev,
                      val,
                      test: remaining - val,
                    }));
                  }}
                />
              </label>
              <label className="export-split-readonly">
                {t("export.test", "Test")}: {(splitRatio.test * 100).toFixed(0)}%
                <span className="export-split-auto-note">{t("export.testAuto")}</span>
              </label>
            </div>
          </div>

          <div className="config-section">
            <h3>{t("export.stratify", "Stratify By")}</h3>
            <div className="stratify-options">
              {["district", "time_of_day", "weather", "node_id"].map((s) => (
                <label key={s}>
                  <input
                    type="checkbox"
                    checked={stratify.includes(s)}
                    onChange={(e) => {
                      if (e.target.checked) setStratify([...stratify, s]);
                      else setStratify(stratify.filter((x) => x !== s));
                    }}
                  />
                  {s.replace("_", " ")}
                </label>
              ))}
            </div>
          </div>

          <div className="config-section">
            <h3>{t("export.augmentations", "Augmentations")}</h3>
            {!expertMode ? (
              <p className="help-text">{t("export.basicAugHint", "Enable Expert mode in Settings for advanced augmentation controls.")}</p>
            ) : (
            <div className="aug-grid">
              <label className="aug-toggle">
                <input
                  type="checkbox"
                  checked={augmentations.horizontal_flip}
                  onChange={(e) => updateAug("horizontal_flip", e.target.checked)}
                />
                {t("export.flip", "Horizontal Flip")}
              </label>

              <label className="aug-slider">
                {t("export.rotation", "Rotation")}: {augmentations.rotation_degrees}
                <input
                  type="range"
                  min="-30"
                  max="30"
                  step="5"
                  value={augmentations.rotation_degrees}
                  aria-valuemin={-30}
                  aria-valuemax={30}
                  aria-valuenow={augmentations.rotation_degrees}
                  aria-label={t("export.rotation")}
                  onChange={(e) => updateAug("rotation_degrees", parseInt(e.target.value))}
                />
              </label>

              <label className="aug-slider">
                {t("export.brightness", "Brightness")}: {augmentations.brightness_delta > 0 ? "+" : ""}
                {augmentations.brightness_delta}
                <input
                  type="range"
                  min="-0.3"
                  max="0.3"
                  step="0.05"
                  value={augmentations.brightness_delta}
                  aria-valuemin={-0.3}
                  aria-valuemax={0.3}
                  aria-valuenow={augmentations.brightness_delta}
                  aria-label={t("export.brightness")}
                  onChange={(e) => updateAug("brightness_delta", parseFloat(e.target.value))}
                />
              </label>

              <label className="aug-slider">
                {t("export.contrast", "Contrast")}: {augmentations.contrast_delta > 0 ? "+" : ""}
                {augmentations.contrast_delta}
                <input
                  type="range"
                  min="-0.3"
                  max="0.3"
                  step="0.05"
                  value={augmentations.contrast_delta}
                  aria-valuemin={-0.3}
                  aria-valuemax={0.3}
                  aria-valuenow={augmentations.contrast_delta}
                  aria-label={t("export.contrast")}
                  onChange={(e) => updateAug("contrast_delta", parseFloat(e.target.value))}
                />
              </label>

              <label className="aug-slider">
                {t("export.saturation", "Saturation")}: {augmentations.saturation_delta > 0 ? "+" : ""}
                {augmentations.saturation_delta}
                <input
                  type="range"
                  min="-0.3"
                  max="0.3"
                  step="0.05"
                  value={augmentations.saturation_delta}
                  aria-valuemin={-0.3}
                  aria-valuemax={0.3}
                  aria-valuenow={augmentations.saturation_delta}
                  aria-label={t("export.saturation", "Saturation")}
                />
              </label>

              <label className="aug-toggle">
                <input
                  type="checkbox"
                  checked={augmentations.mosaic}
                  onChange={(e) => updateAug("mosaic", e.target.checked)}
                />
                {t("export.mosaic", "Mosaic (4-image grid)")}
              </label>

              <label className="aug-toggle">
                <input
                  type="checkbox"
                  checked={augmentations.mixup}
                  onChange={(e) => updateAug("mixup", e.target.checked)}
                />
                {t("export.mixup", "MixUp (alpha=0.2)")}
              </label>
            </div>
            )}
          </div>

          <button className="preview-btn" onClick={generatePreview} disabled={isGenerating}>
            {isGenerating ? t("export.generating", "Generating...") : t("export.generatePreview", "Generate Preview")}
          </button>
        </div>

        <div className="export-preview-pane">
          <h3>{t("export.previewTitle", "Preview")} ({previewImages.length} {t("export.samples", "samples")})</h3>

          {previewImages.length === 0 && !isGenerating && (
            <div className="preview-placeholder">
              <p>{t("export.clickPreview", "Click \"Generate Preview\" to see augmentations applied")}</p>
            </div>
          )}

          {isGenerating && (
            <div className="preview-loading">
              <div className="spinner" />
              <p>{t("export.rendering", "Rendering augmented samples...")}</p>
            </div>
          )}

          <div className="preview-grid">
            {previewImages.map((img, idx) => (
              <div key={idx} className="preview-card">
                <div className="preview-comparison">
                  <div className="preview-side">
                    <span className="preview-label">{t("export.original", "Original")}</span>
                    <img src={img.original_url} alt="Original" />
                  </div>
                  <div className="preview-arrow">-&gt;</div>
                  <div className="preview-side">
                    <span className="preview-label">{t("export.augmented", "Augmented")}</span>
                    <img src={img.augmented_url} alt="Augmented" />
                  </div>
                </div>
                <div className="preview-meta">
                  <span className={img.annotations_transformed ? "transformed" : "unchanged"}>
                    {img.annotations_transformed
                      ? t("export.labelsTransformed", "Labels transformed")
                      : t("export.labelsUnchanged", "Labels unchanged")}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {previewImages.length > 0 && (
            <div className="build-section">
              <button className="build-btn" onClick={buildExport} disabled={isBuilding}>
                {isBuilding ? `${t("export.building", "Building...")} ${buildStatus}` : t("export.buildFinal", "Build Final Export")}
              </button>
              {buildJobId && buildStatus === "COMPLETED" && (
                <p className="build-success">{t("export.ready", "Export ready! Download started.")}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </PageShell>
  );
};
