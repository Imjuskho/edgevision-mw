import React, { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { usePageVisible } from "../../hooks/usePageVisible";
import api from "../../services/api";
import { Button, EmptyState, ErrorState, RingGauge, Skeleton, StatCard } from "../ui";

interface HealthScore {
  overall_score: number;
  completeness_pct: number;
  accuracy_pct: number;
  consistency_pct: number;
  timeliness_pct: number;
  recommendations: string[];
}

interface ClassData {
  class_name: string;
  count: number;
  percentage: number;
}

interface ClassDistributionEntry {
  count: number;
  percentage: number;
}

async function fetchHealthMetrics(datasetId: string) {
  const [healthRes, distRes] = await Promise.all([
    api.get(`/studio/datasets/${datasetId}/health`),
    api.get(`/studio/datasets/${datasetId}/class-distribution`).catch(() => ({ data: {} })),
  ]);

  const raw: Record<string, ClassDistributionEntry> = distRes.data;
  const classDist: ClassData[] = Object.entries(raw).map(([cls, v]) => ({
    class_name: cls,
    count: v.count,
    percentage: v.percentage,
  }));

  return { health: healthRes.data as HealthScore, classDist };
}

interface Props {
  datasetId: string;
  onNavigate?: (path: string) => void;
}

const COLORS = ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#fb923c", "#2dd4bf", "#e879f9"];

export const HealthDashboard: React.FC<Props> = ({ datasetId, onNavigate }) => {
  const { t } = useTranslation();
  const pageVisible = usePageVisible();
  const [health, setHealth] = useState<HealthScore | null>(null);
  const [classDist, setClassDist] = useState<ClassData[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const { health, classDist } = await fetchHealthMetrics(datasetId);
      setHealth(health);
      setClassDist(classDist);
      setLastUpdated(new Date());
    } catch (err) {
      console.error("Failed to load health data:", err);
      setHealth(null);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId) return;
    const load = async () => {
      try {
        const { health, classDist } = await fetchHealthMetrics(datasetId);
        setHealth(health);
        setClassDist(classDist);
        setLastUpdated(new Date());
      } catch (err) {
        console.error("Failed to load health data:", err);
        setHealth(null);
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    };
    void load();
    const interval = setInterval(() => {
      if (document.visibilityState !== "hidden") void load();
    }, 300000);
    return () => clearInterval(interval);
  }, [datasetId, pageVisible]);

  if (loading && !health) {
    return (
      <div className="page-shell health-dashboard-page">
        <Skeleton className="health-dashboard-skeleton" />
      </div>
    );
  }

  if (loadError || !health) {
    return (
      <div className="page-shell health-dashboard-page">
        <ErrorState
          title={t("healthPanel.failedToLoad")}
          body={t("health.emptyBody", "Metrics are not available for this dataset yet.")}
          onRetry={() => void loadData()}
          retryLabel={t("health.refresh")}
        />
      </div>
    );
  }

  return (
    <div className="page-shell health-dashboard-page">
      <header className="page-accent-header page-accent--health">
        <div className="page-accent-header-text">
          <h1>{t("health.title")}</h1>
          <p>{t("health.subtitle", "Dataset quality metrics, class balance, and recommended actions.")}</p>
        </div>
        <div className="page-accent-actions">
          <span className="hd-updated">{t("healthPanel.lastUpdated")}: {lastUpdated.toLocaleTimeString()}</span>
          <Button variant="secondary" size="sm" className="hd-refresh" onClick={() => void loadData()}>
            {t("health.refresh")}
          </Button>
        </div>
      </header>
      <div className="health-dashboard">

      <div className="hd-score-grid hd-score-grid--statcards">
        <StatCard
          label={t("health.overall")}
          value={<RingGauge value={health.overall_score} size={72} />}
        />
        <StatCard label={t("health.completeness")} value={`${health.completeness_pct.toFixed(0)}%`} />
        <StatCard label={t("health.accuracy")} value={`${health.accuracy_pct.toFixed(0)}%`} />
        <StatCard label={t("health.consistency")} value={`${health.consistency_pct.toFixed(0)}%`} />
      </div>

      {classDist.length === 0 ? (
        <EmptyState
          title={t("health.emptyClassesTitle", "No class distribution yet")}
          body={t("health.emptyClassesBody", "Label images to populate class metrics.")}
        />
      ) : (
      <div className="hd-charts-row">
        <div className="hd-chart-panel">
          <h3>{t("healthPanel.classDistribution")}</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={classDist}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={4}
                dataKey="percentage"
                nameKey="class_name"
                label={(props) => {
                  const row = props.payload as ClassData;
                  return `${row.class_name}: ${Number(props.value).toFixed(0)}%`;
                }}
              >
                {classDist.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value, _name, props) => [
                  `${Number(value).toFixed(1)}% (${props.payload.count} images)`,
                  props.payload.class_name,
                ]}
              />
            </PieChart>
          </ResponsiveContainer>

          <ResponsiveContainer width="100%" height={Math.max(100, classDist.length * 40)}>
            <BarChart data={classDist} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" domain={[0, 100]} stroke="#94a3b8" />
              <YAxis dataKey="class_name" type="category" stroke="#e2e8f0" width={70} />
              <Tooltip
                contentStyle={{ background: "#1e293b", border: "1px solid #334155" }}
                formatter={(value) => [`${Number(value).toFixed(1)}%`, "Current"]}
              />
              <Bar dataKey="percentage" fill="#60a5fa" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="hd-chart-panel">
          <h3>{t("healthPanel.recommendations")}</h3>
          {health.recommendations.length === 0 ? (
            <p className="hd-no-actions">{t("healthPanel.noRecommendations")}</p>
          ) : (
            <div className="hd-actions-list">
              {health.recommendations.map((rec, idx) => (
                <div key={idx} className="hd-action-card severity-info">
                  <div className="hd-action-content">
                    <p className="hd-action-message">{rec}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      )}

      <div className="hd-quick-actions">
        <button onClick={() => onNavigate?.("/dedup")}>
          {t("healthPanel.runDedup")}
        </button>
        <button onClick={() => onNavigate?.("/export")}>
          {t("healthPanel.buildExport")}
        </button>
      </div>
    </div>
    </div>
  );
};
