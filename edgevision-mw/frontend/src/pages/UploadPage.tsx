import { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import CameraCapture from "../components/CameraCapture";
import ScreenCapture from "../components/ScreenCapture";
import { Button, FormField, Input, ProgressBar, Tabs } from "../components/ui";

interface UploadedFile {
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  progress: number;
  result?: { filename: string; annotation_id: string; status: string };
  error?: string;
}

interface Props {
  datasetId?: string;
  onUploaded?: () => void;
}

type CaptureMode = "file" | "webcam" | "screen" | "url";

const ACCEPTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

const ACCEPTED_VIDEO_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/x-matroska",
  "video/webm",
  "video/hevc",
  "video/x-hevc",
] as const;

const ACCEPTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const ACCEPTED_VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".mkv", ".webm", ".hevc"];

function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function isAcceptedUploadFile(file: File): boolean {
  const mime = file.type.split(";", 1)[0].trim().toLowerCase();
  if ([...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_VIDEO_TYPES].includes(mime as typeof ACCEPTED_IMAGE_TYPES[number] | typeof ACCEPTED_VIDEO_TYPES[number])) {
    return true;
  }
  const ext = fileExtension(file.name);
  return ACCEPTED_IMAGE_EXTENSIONS.includes(ext) || ACCEPTED_VIDEO_EXTENSIONS.includes(ext);
}

export default function UploadPage({
  datasetId: initialDatasetId,
  onUploaded,
}: Props) {
  const { t } = useTranslation();
  const [datasetId, setDatasetId] = useState(initialDatasetId || "");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [summary, setSummary] = useState<{
    uploaded: number;
    skipped: number;
    total: number;
  } | null>(null);

  useEffect(() => {
    setDatasetId(initialDatasetId || "");
  }, [initialDatasetId]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<CaptureMode>("file");
  const [urlInput, setUrlInput] = useState("");

  const isDatasetLocked = Boolean(initialDatasetId?.trim());

  const acceptedTypes = [...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_VIDEO_TYPES];
  const acceptAttribute = [
    ...acceptedTypes,
    ...ACCEPTED_IMAGE_EXTENSIONS,
    ...ACCEPTED_VIDEO_EXTENSIONS,
  ].join(",");

  const addFiles = useCallback((incoming: File[]) => {
    const accepted = incoming.filter(isAcceptedUploadFile);
    const rejected = incoming.length - accepted.length;
    if (rejected > 0) {
      setUploadError(t("upload.rejectedFiles", "{{count}} file(s) skipped — unsupported format.", { count: rejected }));
    }
    if (accepted.length === 0) return;
    setFiles((prev) => [
      ...prev,
      ...accepted.map((file) => ({
        file,
        status: "pending" as const,
        progress: 0,
      })),
    ]);
  }, [t]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(Array.from(e.dataTransfer.files));
  }, [addFiles]);

  const onFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    addFiles(Array.from(e.target.files));
  }, [addFiles]);

  const resolveSource = (source: CaptureMode | string) =>
    source === "screen" ? "screen_capture" : source;

  const onCapture = useCallback((blob: Blob, filename: string) => {
    const file = new File([blob], filename, { type: blob.type || "image/jpeg" });
    setFiles((prev) => [
      ...prev,
      { file, status: "pending" as const, progress: 0 },
    ]);
  }, []);

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const clearFiles = () => {
    setFiles([]);
    setSummary(null);
    setUploadError(null);
  };

  const applyUploadResults = (
    data: {
      uploaded: number;
      skipped: number;
      total: number;
      images?: { filename: string; status: string; annotation_id: string }[];
      errors?: { filename: string; error: string }[];
    },
  ) => {
    const errorByName = new Map((data.errors ?? []).map((entry) => [entry.filename, entry.error]));
    const resultByName = new Map((data.images ?? []).map((entry) => [entry.filename, entry]));

    setSummary({
      uploaded: data.uploaded,
      skipped: data.skipped,
      total: data.total,
    });

    if (data.uploaded === 0 && (data.errors?.length ?? 0) > 0) {
      setUploadError(
        t("upload.allFailed", "No files uploaded. {{count}} file(s) failed validation.", {
          count: data.errors?.length ?? 0,
        }),
      );
    } else if ((data.errors?.length ?? 0) > 0) {
      setUploadError(
        t("upload.partialFailed", "{{count}} file(s) failed validation.", {
          count: data.errors?.length ?? 0,
        }),
      );
    }

    setFiles((prev) =>
      prev.map((f) => {
        const errMsg = errorByName.get(f.file.name);
        if (errMsg) {
          return { ...f, status: "error" as const, progress: 0, error: errMsg };
        }
        const result = resultByName.get(f.file.name);
        if (result?.status === "uploaded") {
          return { ...f, status: "done" as const, progress: 100, result };
        }
        if (result?.status === "skipped_duplicate") {
          return {
            ...f,
            status: "done" as const,
            progress: 100,
            result,
            error: t("upload.duplicatesFound"),
          };
        }
        if (f.status === "pending") {
          return { ...f, status: "error" as const, error: t("upload.uploadFailed") };
        }
        return f;
      }),
    );
  };

  const uploadAll = async (overrideSource?: string) => {
    if (!datasetId.trim() || files.length === 0) return;
    setUploading(true);
    setSummary(null);
    setUploadError(null);

    const formData = new FormData();
    formData.append("dataset_id", datasetId.trim());
    formData.append("source", overrideSource || resolveSource(mode));
    files.forEach((file) => formData.append("files", file.file));

    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch("/api/v1/upload/images", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!resp.ok) {
        let detail = "Upload failed";
        try {
          const err = await resp.json();
          detail = err.detail || detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }

      const data = await resp.json();
      applyUploadResults(data);
      onUploaded?.();
    } catch (err) {
      const msg = String(err);
      setUploadError(msg);
      setFiles((prev) =>
        prev.map((f) =>
          f.status === "pending" ? { ...f, status: "error" as const, error: msg } : f,
        ),
      );
    } finally {
      setUploading(false);
    }
  };

  const uploadUrl = async () => {
    if (!datasetId.trim() || !urlInput.trim()) return;
    setUploading(true);
    setSummary(null);
    setUploadError(null);

    const formData = new FormData();
    formData.append("dataset_id", datasetId.trim());
    formData.append("url", urlInput.trim());
    formData.append("source", "url");

    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch("/api/v1/upload/url", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!resp.ok) {
        let detail = "Upload failed";
        try {
          const err = await resp.json();
          detail = err.detail || detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }

      const data = await resp.json();
      setSummary({
        uploaded: data.uploaded,
        skipped: data.skipped,
        total: data.total,
      });

      onUploaded?.();
    } catch (err) {
      setUploadError(String(err));
    } finally {
      setUploading(false);
    }
  };

  const capturedCount = files.length;
  const modeTabs = (["file", "webcam", "screen", "url"] as CaptureMode[]).map((m) => ({
    id: m,
    label: t(`upload.modes.${m}`),
  }));

  return (
    <PageShell
      accent="data"
      className="upload-page"
      title={t("upload.title", "Upload Media")}
      subtitle={t("upload.subtitle", "Upload images or iPhone/device video (MOV/HEVC). Video is sampled into frames for annotation.")}
      badge={datasetId || undefined}
    >
      <div className="upload-card">
        <FormField
          label={isDatasetLocked ? t("upload.datasetLocked") : t("upload.datasetId")}
          hint={isDatasetLocked ? t("upload.datasetLockedHint") : undefined}
          htmlFor="upload-dataset-id"
        >
          <Input
            id="upload-dataset-id"
            type="text"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            readOnly={isDatasetLocked}
            disabled={isDatasetLocked}
            placeholder="DS-LILONGWE-001"
            aria-readonly={isDatasetLocked}
            className="text-mono"
          />
        </FormField>

        <Tabs
          tabs={modeTabs}
          activeId={mode}
          onChange={(id) => {
            setMode(id as CaptureMode);
            setSummary(null);
            setUploadError(null);
          }}
          className="upload-tabs"
        />

        <div className="upload-mode-panel">
          {mode === "file" && (
            <>
              <div
                className={`drop-zone${dragging ? " dragging" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") inputRef.current?.click(); }}
              >
                <div>{t("upload.dropzone", "Drag and drop images or video here, or click to browse")}</div>
                <div className="upload-note">{t("upload.supportedFormats")}</div>
                <div className="upload-note">{t("upload.videoNote")}</div>
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept={acceptAttribute}
                  onChange={onFileSelect}
                  className="upload-input-hidden"
                />
              </div>

              <div className="upload-note upload-note-centered">
                <small>
                  Mobile: use{" "}
                  <label className="upload-camera-label">
                    <input
                      type="file"
                      accept="image/*"
                      capture="environment"
                      onChange={onFileSelect}
                      className="upload-input-hidden"
                    />
                    Camera
                  </label>{" "}
                  to capture from your device camera directly
                </small>
              </div>
            </>
          )}

          {mode === "webcam" && (
            <CameraCapture onCapture={onCapture} capturedCount={capturedCount} />
          )}

          {mode === "screen" && (
            <ScreenCapture onCapture={onCapture} capturedCount={capturedCount} />
          )}

          {mode === "url" && (
            <div className="url-input-area">
              <Input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="https://example.com/image.jpg"
              />
              <div className="upload-actions-row upload-url-actions">
                <Button
                  variant="primary"
                  onClick={() => void uploadUrl()}
                  disabled={uploading || !urlInput.trim() || !datasetId.trim()}
                  loading={uploading}
                >
                  {uploading ? t("upload.uploading") : t("upload.fetchUpload", "Fetch & Upload")}
                </Button>
              </div>
            </div>
          )}
        </div>

        {files.length > 0 && (
          <div className="upload-list">
            {files.map((f, i) => (
              <div key={i} className="upload-list-item">
                <span className="upload-list-name">{f.file.name}</span>
                <span className="upload-list-size">{(f.file.size / 1024).toFixed(0)} KB</span>
                {f.status === "uploading" && (
                  <ProgressBar value={f.progress} aria-label={f.file.name} />
                )}
                {f.status === "done" && !f.error && (
                  <span className="upload-list-status--ok" aria-label="Uploaded">✓</span>
                )}
                {f.status === "done" && f.error && (
                  <span className="upload-list-status--err" title={f.error}>⊘</span>
                )}
                {f.status === "error" && (
                  <span className="upload-list-status--err" aria-label="Error">✗</span>
                )}
                {f.status === "pending" && (
                  <Button variant="ghost" size="sm" onClick={() => removeFile(i)} aria-label="Remove">
                    ×
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}

        {summary && (
          <div className="upload-summary-banner upload-note">
            {t("upload.summary", {
              uploaded: summary.uploaded,
              skipped: summary.skipped,
              total: summary.total,
              defaultValue: `${summary.uploaded} uploaded, ${summary.skipped} skipped, ${summary.total} total`,
            })}
          </div>
        )}

        {uploadError && (
          <div className="upload-error-banner upload-note" role="alert">
            {uploadError}
          </div>
        )}

        {mode !== "url" && (
          <div className="upload-actions-row">
            <Button
              variant="primary"
              onClick={() => void uploadAll()}
              disabled={uploading || files.length === 0 || !datasetId.trim()}
              loading={uploading}
            >
              {uploading
                ? t("upload.uploading")
                : `${t("upload.uploadButton")}${files.length > 0 ? ` (${files.length})` : ""}`}
            </Button>
            {files.length > 0 && (
              <Button variant="secondary" onClick={clearFiles} disabled={uploading}>
                {t("upload.clear", "Clear")}
              </Button>
            )}
            {files.length === 0 && (
              <span className="upload-note">{t("upload.noFiles")}</span>
            )}
            {files.length > 0 && !datasetId.trim() && (
              <span className="upload-note upload-warning-text">
                {t("upload.datasetRequired", "Enter a Dataset ID to enable upload")}
              </span>
            )}
          </div>
        )}
      </div>
    </PageShell>
  );
}
