import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import { studioApi } from "../services/api";
import type { AgriAnalysisReport } from "../types";
import { toStyle } from "../utils/toStyle";

interface AgriAnalysisPageProps {
  datasetId: string;
}

export default function AgriAnalysisPage({ datasetId }: AgriAnalysisPageProps) {
  const { t } = useTranslation();
  const [report, setReport] = useState<AgriAnalysisReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!datasetId) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await studioApi.analyzeAgriCondition(datasetId);
        setReport(resp.data as AgriAnalysisReport);
      } catch {
        setError(t("agriAnalysis.failed"));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [datasetId, t]);

  const getHealthTone = (score: number): "good" | "fair" | "poor" => {
    if (score >= 0.7) return "good";
    if (score >= 0.4) return "fair";
    return "poor";
  };

  const getPressureTone = (level: string): "low" | "medium" | "high" => {
    switch (level) {
      case "low": return "low";
      case "medium": return "medium";
      case "high": return "high";
      default: return "low";
    }
  };

  const cropBarClass = (type: string) => {
    if (type === "maize" || type === "rice" || type === "cassava") return `analysis-bar-fill--${type}`;
    return "analysis-bar-fill--healthy";
  };

  const healthBarClass = (cond: string) => {
    const known = ["healthy", "diseased", "pest_infested", "stressed", "water_logged", "drought_stressed"];
    return known.includes(cond) ? `analysis-bar-fill--${cond}` : "analysis-bar-fill--diseased";
  };

  return (
    <PageShell
      accent="analysis"
      title={t("agriAnalysis.title")}
      subtitle={t("agriAnalysis.subtitle", "Crop health, weed pressure, and pest risk from field imagery.")}
      badge={datasetId || undefined}
    >
      {loading && (
        <div className="analysis-loading">
          <div className="spinner" />
          <p>{t("agriAnalysis.loading")}</p>
        </div>
      )}

      {error && <div className="analysis-error">{error}</div>}

      {report && !loading && (
        <>
          <div className="analysis-cards">
            <div className={`analysis-card analysis-card--health-${getHealthTone(report.health_score)}`}>
              <h3>{t("agriAnalysis.healthScore")}</h3>
              <div className="analysis-big-number">{(report.health_score * 100).toFixed(0)}%</div>
              <span className={`analysis-badge analysis-badge--${getHealthTone(report.health_score)}`}>
                {getHealthTone(report.health_score) === "good" ? t("agriAnalysis.good") : getHealthTone(report.health_score) === "fair" ? t("agriAnalysis.fair") : t("agriAnalysis.poor")}
              </span>
            </div>
            <div className="analysis-card">
              <h3>{t("agriAnalysis.weedPressure")}</h3>
              <div className={`analysis-big-number analysis-value--${getPressureTone(report.weed_pressure)}`}>
                {report.weed_pressure.toUpperCase()}
              </div>
            </div>
            <div className="analysis-card">
              <h3>{t("agriAnalysis.pestRisk")}</h3>
              <div className={`analysis-big-number analysis-value--${getPressureTone(report.pest_risk)}`}>
                {report.pest_risk.toUpperCase()}
              </div>
            </div>
            <div className="analysis-card">
              <h3>{t("agriAnalysis.imagesAnalyzed")}</h3>
              <div className="analysis-big-number">{report.total_images}</div>
            </div>
          </div>

          <div className="analysis-section">
            <h3>{t("agriAnalysis.cropBreakdown")}</h3>
            <div className="analysis-bars">
              {Object.entries(report.crop_breakdown).map(([type, pct]) => (
                <div key={type} className="analysis-bar-row">
                  <span>{type}</span>
                  <div className="analysis-bar-track">
                    <div
                      className={`analysis-bar-fill ${cropBarClass(type)}`}
                      style={toStyle({ width: `${(pct * 100).toFixed(1)}%` })}
                    />
                  </div>
                  <span>{(pct * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="analysis-section">
            <h3>{t("agriAnalysis.healthBreakdown")}</h3>
            <div className="analysis-bars">
              {Object.entries(report.health_breakdown).map(([cond, pct]) => (
                <div key={cond} className="analysis-bar-row">
                  <span>{cond}</span>
                  <div className="analysis-bar-track">
                    <div
                      className={`analysis-bar-fill ${healthBarClass(cond)}`}
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
              <h3>{t("agriAnalysis.recommendedAction")}</h3>
              <p>{report.recommended_action}</p>
            </div>
          )}
        </>
      )}

      {!datasetId && !loading && (
        <div className="analysis-empty">
          <p>{t("agriAnalysis.noData")}</p>
        </div>
      )}
    </PageShell>
  );
}
