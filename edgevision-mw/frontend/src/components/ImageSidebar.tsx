import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ImageItem } from "../types";
import { studioApi } from "../services/api";

interface Props {
  datasetId: string;
  currentIndex: number;
  onSelect: (index: number) => void;
}

export default function ImageSidebar({ datasetId, currentIndex, onSelect }: Props) {
  const { t } = useTranslation();
  const [images, setImages] = useState<ImageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [prevDatasetId, setPrevDatasetId] = useState(datasetId);
  if (datasetId !== prevDatasetId) {
    setPrevDatasetId(datasetId);
    setLoading(true);
    setError(false);
  }

  useEffect(() => {
    let cancelled = false;
    studioApi
      .listImages(datasetId, 1, 200)
      .then((resp) => {
        if (!cancelled) setImages(resp.data.images);
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setImages([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const labeled = images.filter((img) => img.has_human_labels).length;

  return (
    <div className="image-sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">{t("sidebar.images")}</span>
        <span className="sidebar-count">{labeled}/{images.length}</span>
      </div>

      <div className="sidebar-list">
        {loading && (
          <p className="empty-state sidebar-status">{t("sidebar.loading")}</p>
        )}
        {error && (
          <p className="error-notice sidebar-status">{t("sidebar.loadFailed")}</p>
        )}
        {!loading && !error && images.length === 0 && (
          <p className="empty-state sidebar-status">{t("sidebar.empty")}</p>
        )}
        {images.map((img, idx) => (
          <button
            key={img.annotation_id}
            onClick={() => onSelect(idx)}
            className={`sidebar-item ${idx === currentIndex ? "active" : ""}`}
            aria-label={`${t("sidebar.images")} #${img.index}`}
          >
            <span className="sidebar-item-index">#{img.index}</span>
            <span
              className={`sidebar-item-dot ${
                img.has_human_labels
                  ? "sidebar-item-dot--labeled"
                  : img.status === "CERTIFIED"
                    ? "sidebar-item-dot--certified"
                    : "sidebar-item-dot--default"
              }`}
            />
          </button>
        ))}
      </div>
    </div>
  );
}
