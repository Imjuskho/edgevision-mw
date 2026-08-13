import { useTranslation } from "react-i18next";
import { ROAD_CLASS_ARRAY, getRoadClassColor, ROAD_CLASS_DISPLAY_NAMES } from "../../constants/roadTaxonomy";
import type { RoadSegAnnotation, InstanceMask } from "../../types";
import { toStyle } from "../../utils/toStyle";

interface RoadSegPanelProps {
  isActive: boolean;
  annotations: RoadSegAnnotation[];
  instances: InstanceMask[];
  isProcessing: boolean;
  isSegmenting: boolean;
  error: string | null;
  onToggleActive: () => void;
  onAutoSegment: () => void;
  onAcceptInstance: (id: string) => void;
  onRejectInstance: (id: string) => void;
  onAcceptAll: () => void;
  onRejectAll: () => void;
  onClearInstances: () => void;
  onSave: () => void;
}

export function RoadSegPanel({
  isActive,
  annotations,
  instances,
  isProcessing,
  isSegmenting,
  error,
  onToggleActive,
  onAutoSegment,
  onAcceptInstance,
  onRejectInstance,
  onAcceptAll,
  onRejectAll,
  onClearInstances,
  onSave,
}: RoadSegPanelProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith("ny") ? "ny" : "en";

  const acceptedCount = annotations.filter((a) => a.accepted).length;
  const rejectedCount = annotations.filter((a) => !a.accepted).length;

  const goodRoadPct = instances.length > 0
    ? Math.round(
        (instances.filter((i) => i.class_name === "good_road").length /
          instances.length) *
          100
      )
    : 0;

  const isBusy = isProcessing || isSegmenting;

  return (
    <div className={`road-seg-panel ${isActive ? "active" : ""}`}>
      <div className="road-seg-header">
        <div className="road-seg-header-top">
          <h3>{t("roadSegmentation.title")}</h3>
          <span className={`road-seg-badge ${isActive ? "active" : ""}`}>
            {isActive ? t("roadSegmentation.active") : t("roadSegmentation.inactive")}
          </span>
        </div>
        <p className="road-seg-subtitle">{t("roadSegmentation.subtitle")}</p>
      </div>

      {error && (
        <div className="road-seg-error">
          <span className="road-seg-error-icon">!</span>
          <span>{error}</span>
        </div>
      )}

      <div className="road-seg-mode-toggle">
        <button
          type="button"
          className={`road-seg-mode-btn ${isActive ? "active" : ""}`}
          onClick={onToggleActive}
          aria-pressed={isActive}
        >
          <span className="road-seg-mode-icon">{isActive ? "✏️" : "👆"}</span>
          <span className="road-seg-mode-label">
            {isActive ? t("roadSegmentation.drawingMode") : t("roadSegmentation.selectMode")}
          </span>
        </button>
      </div>

      <div className="road-seg-actions">
        <button
          type="button"
          className="road-seg-btn road-seg-btn-primary"
          onClick={onAutoSegment}
          disabled={isBusy}
        >
          {isBusy ? (
            <>
              <span className="road-seg-spinner" />
              {t("roadSegmentation.segmenting")}
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
              {t("roadSegmentation.autoSegment")}
            </>
          )}
        </button>

        <div className="road-seg-btn-group">
          <button
            type="button"
            className="road-seg-btn road-seg-btn-accept"
            onClick={onAcceptAll}
            disabled={annotations.length === 0 || isBusy}
          >
            ✓ {t("roadSegmentation.acceptAll")}
          </button>
          <button
            type="button"
            className="road-seg-btn road-seg-btn-reject"
            onClick={onRejectAll}
            disabled={annotations.length === 0 || isBusy}
          >
            ✕ {t("roadSegmentation.rejectAll")}
          </button>
          <button
            type="button"
            className="road-seg-btn road-seg-btn-clear"
            onClick={onClearInstances}
            disabled={annotations.length === 0 || isBusy}
          >
            {t("roadSegmentation.clear")}
          </button>
        </div>
      </div>

      {instances.length > 0 && (
        <div className="road-seg-stats-grid">
          <div className="road-seg-stat-card">
            <span className="road-seg-stat-value">{instances.length}</span>
            <span className="road-seg-stat-label">{t("roadSegmentation.total")}</span>
          </div>
          <div className="road-seg-stat-card accept">
            <span className="road-seg-stat-value">{acceptedCount}</span>
            <span className="road-seg-stat-label">{t("roadSegmentation.acceptedLabel")}</span>
          </div>
          <div className="road-seg-stat-card reject">
            <span className="road-seg-stat-value">{rejectedCount}</span>
            <span className="road-seg-stat-label">{t("roadSegmentation.rejectedLabel")}</span>
          </div>
          <div className="road-seg-stat-card">
            <span className="road-seg-stat-value">{goodRoadPct}%</span>
            <span className="road-seg-stat-label">{t("roadSegmentation.goodRoadLabel")}</span>
          </div>
        </div>
      )}

      <div className="road-seg-section">
        <div className="road-seg-section-header">
          <h4>{t("roadSegmentation.legend")}</h4>
        </div>
        <div className="road-seg-class-legend">
          {ROAD_CLASS_ARRAY.map((cls) => (
            <div key={cls.id} className="road-seg-legend-item">
              <span
                className="road-seg-legend-color"
                style={toStyle({ backgroundColor: cls.color })}
              />
              <span className="road-seg-legend-name">
                {ROAD_CLASS_DISPLAY_NAMES[cls.name]?.[lang] ?? cls.name}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="road-seg-section">
        <div className="road-seg-section-header">
          <h4>{t("roadSegmentation.stats")}</h4>
          {annotations.length > 0 && (
            <span className="road-seg-count">{annotations.length}</span>
          )}
        </div>

        <div className="road-seg-annotations">
          {annotations.length === 0 && !isBusy && (
            <div className="road-seg-empty">
              <div className="road-seg-empty-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
              </div>
              <p>{t("roadSegmentation.noInstancesYet")}</p>
              <p className="road-seg-empty-hint">{t("roadSegmentation.noInstancesHint")}</p>
            </div>
          )}

          {isBusy && (
            <div className="road-seg-empty">
              <div className="road-seg-spinner" />
              <p>{t("roadSegmentation.processing")}</p>
            </div>
          )}

          {annotations.map((ann) => (
            <div
              key={ann.id}
              className={`road-seg-ann-item ${ann.accepted ? "accepted" : "rejected"}`}
              style={toStyle({ borderLeftColor: getRoadClassColor(ann.class_id) })}
            >
              <div className="road-seg-ann-color-bar"
                style={toStyle({ backgroundColor: getRoadClassColor(ann.class_id) })}
              />
              <div className="road-seg-ann-body">
                <div className="road-seg-ann-top">
                  <span
                    className="road-seg-ann-class"
                    style={toStyle({ color: getRoadClassColor(ann.class_id) })}
                  >
                    {ROAD_CLASS_DISPLAY_NAMES[ann.class_name]?.[lang] ?? ann.class_name}
                  </span>
                  <div className={`road-seg-ann-conf-badge ${
                    ann.confidence >= 0.7 ? "road-seg-conf-badge--high" :
                    ann.confidence >= 0.4 ? "road-seg-conf-badge--medium" :
                    "road-seg-conf-badge--low"
                  }`}
                  >
                    {(ann.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="road-seg-ann-conf-bar">
                  <div className="road-seg-ann-conf-fill"
                    style={toStyle({
                      width: `${(ann.confidence * 100).toFixed(0)}%`,
                      backgroundColor: getRoadClassColor(ann.class_id),
                    })}
                  />
                </div>
                <div className="road-seg-ann-actions">
                  {ann.accepted ? (
                    <button
                      type="button"
                      className="road-seg-ann-btn reject"
                      onClick={() => onRejectInstance(ann.id)}
                      aria-label={t("roadSegmentation.reject")}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                      {t("roadSegmentation.reject")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="road-seg-ann-btn accept"
                      onClick={() => onAcceptInstance(ann.id)}
                      aria-label={t("roadSegmentation.accept")}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      {t("roadSegmentation.accept")}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {annotations.length > 0 && (
        <button
          type="button"
          className="road-seg-save-btn"
          onClick={onSave}
          disabled={isBusy}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
            <polyline points="17 21 17 13 7 13 7 21" />
            <polyline points="7 3 7 8 15 8" />
          </svg>
          {t("roadSegmentation.save")}
        </button>
      )}
    </div>
  );
}
