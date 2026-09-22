import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import { studioApi } from "../services/api";
import type { RoadConditionReport } from "../types";
import { toStyle } from "../utils/toStyle";

interface RoadAnalysisPageProps {
  datasetId: string;
  onNavigate?: (view: string) => void;
}

export default function RoadAnalysisPage({ datasetId }: RoadAnalysisPageProps) {
  const { t } = useTranslation();
  const [report, setReport] = useState<RoadConditionReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!datasetId) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await studioApi.analyzeRoadCondition(datasetId);
        setReport(resp.data as RoadConditionReport);
      } catch {
        setError(t("roadAnalysis.failed"));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [datasetId, t]);

  const getConditionTone = (score: number): "good" | "fair" | "poor" => {
    if (score >= 0.7) return "good";
    if (score >= 0.4) return "fair";
    return "poor";
  };

  const getSeverityTone = (severity: string): "low" | "medium" | "high" => {
    switch (severity) {
      case "low": return "low";
      case "medium": return "medium";
      case "high": return "high";
      default: return "low";
    }
  };

  const surfaceBarClass = (type: string) => {
    if (type === "paved") return "analysis-bar-fill--paved";
    if (type === "unpaved") return "analysis-bar-fill--unpaved";
    return "analysis-bar-fill--stressed";
  };

  return (
    <PageShell
      accent="analysis"
      title={t("roadAnalysis.title")}
      subtitle={t("roadAnalysis.subtitle", "Condition scoring and surface breakdown from annotated road imagery.")}
      badge={datasetId || undefined}
    >
      {loading && (
        <div className="analysis-loading">
          <div className="spinner" />
          <p>{t("roadAnalysis.loading")}</p>
        </div>
      )}

      {error && <div className="analysis-error">{error}</div>}

      {report && !loading && (
        <>
          <div className="analysis-cards">
            <div className={`analysis-card analysis-card--health-${getConditionTone(report.condition_score)}`}>
              <h3>{t("roadAnalysis.conditionScore")}</h3>
              <div className="analysis-big-number">{(report.condition_score * 100).toFixed(0)}%</div>
              <span className={`analysis-badge analysis-badge--${getConditionTone(report.condition_score)}`}>
                {getConditionTone(report.condition_score) === "good" ? t("roadAnalysis.good") : getConditionTone(report.condition_score) === "fair" ? t("roadAnalysis.fair") : t("roadAnalysis.poor")}
              </span>
            </div>
            <div className="analysis-card">
              <h3>{t("roadAnalysis.potholes")}</h3>
              <div className="analysis-big-number">{report.pothole_count}</div>
              <div className="text-secondary text-sm">
                {report.pothole_density_per_km2.toFixed(1)} {t("roadAnalysis.perKm2")}
              </div>
            </div>
            <div className="analysis-card">
              <h3>{t("roadAnalysis.crackSeverity")}</h3>
              <div className={`analysis-big-number analysis-value--${getSeverityTone(report.crack_severity)}`}>
                {report.crack_severity.toUpperCase()}
              </div>
            </div>
            <div className="analysis-card">
              <h3>{t("roadAnalysis.imagesAnalyzed")}</h3>
              <div className="analysis-big-number">{report.total_images}</div>
            </div>
          </div>

          <div className="analysis-section">
            <h3>{t("roadAnalysis.surfaceBreakdown")}</h3>
            <div className="analysis-bars">
              {Object.entries(report.surface_breakdown).map(([type, pct]) => (
                <div key={type} className="analysis-bar-row">
                  <span>{type}</span>
                  <div className="analysis-bar-track">
                    <div
                      className={`analysis-bar-fill ${surfaceBarClass(type)}`}
                      style={toStyle({ width: `${(pct * 100).toFixed(1)}%` })}
                    />
                  </div>
                  <span>{(pct * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>

          {report.recommended_action && (
            <div className="analysis-section">
              <h3>{t("roadAnalysis.recommendedAction")}</h3>
              <p>{report.recommended_action}</p>
            </div>
          )}
        </>
      )}

      {!datasetId && !loading && (
        <div className="analysis-empty">
          <p>{t("roadAnalysis.noData")}</p>
        </div>
      )}
    </PageShell>
  );
}
