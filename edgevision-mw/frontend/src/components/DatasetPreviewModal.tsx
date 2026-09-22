import { useTranslation } from "react-i18next";
import { Button } from "./ui";

interface DatasetPreviewProps {
  dataset: {
    dataset_id: string;
    name: string;
    sample_count: number;
    classes: Record<string, number>;
    price_usd: number | string;
    license_type: string;
    iaa_score: number;
    consent_coverage_pct: number;
    status: string;
    created_at?: string;
  };
  onClose: () => void;
}

function classEntries(classes: Record<string, number>): [string, number][] {
  return Object.entries(classes)
    .sort((a, b) => b[1] - a[1]);
}

function maxClassCount(classes: Record<string, number>): number {
  const entries = Object.values(classes);
  return entries.length > 0 ? Math.max(...entries) : 1;
}

export function DatasetPreviewModal({ dataset, onClose }: DatasetPreviewProps) {
  const { t } = useTranslation();
  const entries = classEntries(dataset.classes);
  const maxCount = maxClassCount(dataset.classes);

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-label={t("marketplace.previewTitle", "Dataset preview")}>
      <div className="modal-content dataset-preview-modal" onClick={(e) => e.stopPropagation()}>
        <div className="dataset-preview-header">
          <h2>{dataset.name || dataset.dataset_id}</h2>
          <span className="marketplace-status-chip">{dataset.status}</span>
        </div>

        <div className="dataset-preview-stats">
          <div className="dataset-preview-stat">
            <span className="dataset-preview-stat-label">{t("marketplace.samples", "Samples")}</span>
            <span className="dataset-preview-stat-value">{dataset.sample_count.toLocaleString()}</span>
          </div>
          <div className="dataset-preview-stat">
            <span className="dataset-preview-stat-label">{t("marketplace.classes", "Classes")}</span>
            <span className="dataset-preview-stat-value">{entries.length}</span>
          </div>
          <div className="dataset-preview-stat">
            <span className="dataset-preview-stat-label">{t("marketplace.price", "Price")}</span>
            <span className="dataset-preview-stat-value">${Number(dataset.price_usd).toFixed(2)}</span>
          </div>
          <div className="dataset-preview-stat">
            <span className="dataset-preview-stat-label">{t("marketplace.licenseType", "License")}</span>
            <span className="dataset-preview-stat-value">{dataset.license_type}</span>
          </div>
        </div>

        {dataset.iaa_score > 0 && (
          <div className="dataset-preview-scores">
            <div className="dataset-preview-score">
              <span className="dataset-preview-score-label">{t("marketplace.iaaScore", "IAA Score")}</span>
              <div className="dataset-preview-score-bar">
                <div
                  className="dataset-preview-score-fill dataset-preview-score-fill--iaa"
                  style={{ width: `${dataset.iaa_score * 100}%` }}
                />
              </div>
              <span className="dataset-preview-score-value">{(dataset.iaa_score * 100).toFixed(0)}%</span>
            </div>
            <div className="dataset-preview-score">
              <span className="dataset-preview-score-label">{t("marketplace.consentCoverage", "Consent Coverage")}</span>
              <div className="dataset-preview-score-bar">
                <div
                  className="dataset-preview-score-fill dataset-preview-score-fill--consent"
                  style={{ width: `${dataset.consent_coverage_pct}%` }}
                />
              </div>
              <span className="dataset-preview-score-value">{dataset.consent_coverage_pct.toFixed(0)}%</span>
            </div>
          </div>
        )}

        {entries.length > 0 && (
          <div className="dataset-preview-classes">
            <h3>{t("marketplace.classDistribution", "Class Distribution")}</h3>
            <div className="dataset-preview-class-list">
              {entries.map(([label, count]) => (
                <div key={label} className="dataset-preview-class-row">
                  <span className="dataset-preview-class-label" title={label}>{label}</span>
                  <div className="dataset-preview-class-bar">
                    <div
                      className="dataset-preview-class-fill"
                      style={{ width: `${(count / maxCount) * 100}%` }}
                    />
                  </div>
                  <span className="dataset-preview-class-count">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {dataset.created_at && (
          <p className="dataset-preview-created">
            {t("marketplace.created", "Created {{date}}", {
              date: new Date(dataset.created_at).toLocaleDateString(),
            })}
          </p>
        )}

        <div className="dataset-preview-footer">
          <Button variant="secondary" onClick={onClose}>
            {t("common.close", "Close")}
          </Button>
        </div>
      </div>
    </div>
  );
}
