import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Dataset, HealthScore } from "../types";
import type { View } from "../routes/paths";
import { getHomePersonaConfig } from "../utils/homePersona";
import { toStyle } from "../utils/toStyle";
import { Button, EmptyState, ErrorState, RingGauge, StatCard } from "./ui";

interface QuickAction {
  v: View;
  labelKey: string;
  color: string;
  path: string;
}

interface WorkflowGroup {
  sectionKey: string;
  accent: string;
  actions: QuickAction[];
}

interface DashboardHomeProps {
  datasetId: string;
  datasets: Dataset[];
  datasetsTotal?: number;
  health: HealthScore | null;
  healthError: boolean;
  isOnline: boolean;
  pendingSync: number;
  userRole?: string;
  userName?: string;
  showDashboardHealth?: boolean;
  onNavigate: (view: View) => void;
  onBrowseDatasets: () => void;
}

function scoreTone(score: number): "good" | "fair" | "low" {
  if (score >= 75) return "good";
  if (score >= 45) return "fair";
  return "low";
}

function HealthMetric({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  const tone = scoreTone(value);
  const pct = Math.min(100, Math.max(0, value));

  return (
    <div className={`dash-metric dash-metric--${tone}`}>
      <div
        className="dash-metric-ring"
        style={{ "--metric-accent": accent, "--metric-deg": `${pct * 3.6}deg` } as React.CSSProperties}
        aria-hidden
      >
        <span className="dash-metric-value">{value.toFixed(0)}%</span>
      </div>
      <span className="dash-metric-label">{label}</span>
    </div>
  );
}

const WORKFLOW_GROUP_CLASS: Record<string, string> = {
  "nav.sections.labeling": "dash-workflow-group--labeling",
  "nav.sections.data": "dash-workflow-group--data",
  "nav.sections.quality": "dash-workflow-group--quality",
  "nav.sections.analysis": "dash-workflow-group--analysis",
};

const WORKFLOW_GROUPS: WorkflowGroup[] = [
  {
    sectionKey: "nav.sections.labeling",
    accent: "var(--section-labeling)",
    actions: [
      { v: "annotate", labelKey: "nav.annotate", color: "#22c55e", path: "M8 12h8M12 2l10 5-10 5L2 7l10-5z" },
      { v: "agriAnnotate", labelKey: "nav.agriAnnotate", color: "#84cc16", path: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" },
      { v: "segment", labelKey: "nav.segment", color: "#f97316", path: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" },
      { v: "liveAnnotate", labelKey: "nav.liveAnnotate", color: "#14b8a6", path: "M15 10l4.553-4.553a2 2 0 00-2.828-2.828L10 7l-5 3-2 6 6-2 5-4z" },
    ],
  },
  {
    sectionKey: "nav.sections.data",
    accent: "var(--section-data)",
    actions: [
      { v: "upload", labelKey: "nav.upload", color: "#3b82f6", path: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" },
      { v: "dedup", labelKey: "nav.dedup", color: "#ec4899", path: "M16 3h5v5M8 3H3v5M12 22V8M21 3l-9 9" },
      { v: "export", labelKey: "nav.export", color: "#34d399", path: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" },
      { v: "datasets", labelKey: "nav.datasets", color: "#6366f1", path: "M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7M2 4h20M12 12h.01" },
    ],
  },
  {
    sectionKey: "nav.sections.quality",
    accent: "var(--section-quality)",
    actions: [
      { v: "queue", labelKey: "nav.queue", color: "#eab308", path: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" },
    ],
  },
  {
    sectionKey: "nav.sections.analysis",
    accent: "var(--section-analysis)",
    actions: [
      { v: "roadAnalysis", labelKey: "nav.roadAnalysis", color: "#fb923c", path: "M22 12h-4l-3 9L9 3l-3 9H2" },
      { v: "agriAnalysis", labelKey: "nav.agriAnalysis", color: "#a3e635", path: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" },
      { v: "health", labelKey: "nav.health", color: "#ef4444", path: "M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" },
      { v: "training", labelKey: "nav.training", color: "#a855f7", path: "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18" },
      { v: "fleet", labelKey: "nav.fleet", color: "#38bdf8", path: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" },
    ],
  },
];

function ActionIcon({ path, color }: { path: string; color: string }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" aria-hidden>
      {path.split("M").filter(Boolean).map((d, i) => (
        <path key={i} d={`M${d}`} />
      ))}
    </svg>
  );
}

export function DashboardHome({
  datasetId,
  datasets,
  datasetsTotal,
  health,
  healthError,
  isOnline,
  pendingSync,
  userRole,
  userName,
  showDashboardHealth = true,
  onNavigate,
  onBrowseDatasets,
}: DashboardHomeProps) {
  const { t } = useTranslation();

  const persona = getHomePersonaConfig(userRole);

  const activeDataset = useMemo(
    () => datasets.find((d) => (d.dataset_id || d.id) === datasetId),
    [datasets, datasetId],
  );

  const displayName = activeDataset?.name || datasetId;
  const imageCount = activeDataset?.sample_count;
  const overallTone = health ? scoreTone(health.overall_score) : "fair";
  const totalDatasets = datasetsTotal ?? datasets.length;

  return (
    <div className="dash-home">
      <header className="dash-hero">
        <div className="dash-hero-glow" aria-hidden />
        <div className="dash-hero-inner">
          <div className="dash-hero-badge">{t("home.eyebrow", "Malawi field annotation")}</div>
          <h1>{t("home.title")}</h1>
          <p>{t("home.subtitle")}</p>
          <div className="dash-status-row">
            <span className={`dash-pill ${isOnline ? "dash-pill--online" : "dash-pill--offline"}`}>
              {isOnline ? t("nav.online") : t("nav.offline")}
            </span>
            {userRole && <span className="dash-pill dash-pill--role">{userRole}</span>}
            {userName && <span className="dash-pill dash-pill--user">{userName}</span>}
            {pendingSync > 0 && (
              <span className="dash-pill dash-pill--sync">
                {t("sync.pending", { count: pendingSync })}
              </span>
            )}
          </div>
        </div>
      </header>

      {persona.showMarketplacePlaceholder && (
        <EmptyState
          title={t("home.buyerTitle", "Dataset marketplace")}
          body={t("home.buyerBody", "Browse and license certified datasets — coming soon.")}
        />
      )}

      {!persona.showMarketplacePlaceholder && persona.persona === "ANNOTATOR" && (
        <section className="dash-persona-panel dash-persona-panel--annotator">
          <h2>{t("home.annotatorToday", "Today's work")}</h2>
          <div className="dash-persona-stats">
            {pendingSync > 0 && (
              <StatCard label={t("sync.pendingLabel", "Pending sync")} value={pendingSync} />
            )}
            {datasetId && (
              <StatCard label={t("home.activeDataset")} value={displayName} />
            )}
          </div>
          {datasetId && (
            <Button variant="primary" onClick={() => onNavigate("annotate")}>
              {t("home.startAnnotation")}
            </Button>
          )}
        </section>
      )}

      {!persona.showMarketplacePlaceholder && (persona.persona === "QA" || persona.persona === "ADMIN") && (
        <section className="dash-persona-panel dash-persona-panel--qa">
          <h2>{t("home.qaOverview", "Quality overview")}</h2>
          <div className="dash-persona-stats">
            <StatCard label={t("home.datasetsTotal", "Datasets")} value={totalDatasets} />
            {datasetId ? (
              <>
                <StatCard label={t("home.activeDataset")} value={displayName} className="ui-stat-card--truncate" />
                {imageCount != null && (
                  <StatCard
                    label={t("home.imagesLabel", "Images")}
                    value={imageCount.toLocaleString()}
                  />
                )}
              </>
            ) : (
              health &&
              showDashboardHealth && (
                <StatCard
                  label={t("home.datasetHealth")}
                  value={<RingGauge value={health.overall_score} size={56} />}
                  className="ui-stat-card--gauge"
                />
              )
            )}
          </div>
        </section>
      )}

      {!persona.showMarketplacePlaceholder && persona.persona === "OPERATOR" && (
        <section className="dash-persona-panel dash-persona-panel--operator">
          <h2>{t("home.operatorOverview", "Operations")}</h2>
          <div className="dash-persona-actions">
            <Button variant="secondary" onClick={() => onNavigate("fleet")}>{t("nav.fleet")}</Button>
            <Button variant="secondary" onClick={() => onNavigate("upload")}>{t("nav.upload")}</Button>
            <Button variant="secondary" onClick={() => onNavigate("export")}>{t("nav.export")}</Button>
          </div>
        </section>
      )}

      {!persona.showMarketplacePlaceholder && persona.persona === "FIELD_TECH" && (
        <section className="dash-persona-panel dash-persona-panel--field">
          <h2>{t("home.fieldOverview", "Field systems")}</h2>
          <div className="dash-persona-actions">
            <Button variant="secondary" onClick={() => onNavigate("fleet")}>{t("nav.fleet")}</Button>
            <Button variant="secondary" onClick={() => onNavigate("datasets")}>{t("nav.datasets")}</Button>
          </div>
        </section>
      )}

      {!datasetId && !persona.showMarketplacePlaceholder && (
        <section className="dash-onboarding">
          <div className="dash-onboarding-grid">
            <article className="dash-step-card dash-step-card--green">
              <span className="dash-step-num">1</span>
              <h3>{t("home.stepBrowseTitle", "Browse datasets")}</h3>
              <p>{t("home.stepBrowseDesc", "Find road, agriculture, or custom collections captured in the field.")}</p>
            </article>
            <article className="dash-step-card dash-step-card--blue">
              <span className="dash-step-num">2</span>
              <h3>{t("home.stepSelectTitle", "Select a dataset")}</h3>
              <p>{t("home.stepSelectDesc", "Use the sidebar dropdown or dataset browser to set your working context.")}</p>
            </article>
            <article className="dash-step-card dash-step-card--teal">
              <span className="dash-step-num">3</span>
              <h3>{t("home.stepWorkTitle", "Start labeling")}</h3>
              <p>{t("home.stepWorkDesc", "Annotate, segment roads, run live capture, or train models on your data.")}</p>
            </article>
          </div>
          <div className="dash-cta-panel">
            <div>
              <h2>{t("home.browseDatasets")}</h2>
              <p>{t("home.browseDatasetsHint")}</p>
            </div>
            <button type="button" className="btn btn-primary btn-lg" onClick={onBrowseDatasets}>
              {t("home.browseDatasetsButton")}
            </button>
          </div>
        </section>
      )}

      {datasetId && (
        <div className="dash-body">
          <section className={`dash-dataset-banner dash-dataset-banner--${overallTone}`}>
            <div className="dash-dataset-banner-main">
              <span className="dash-dataset-label">{t("home.activeDataset")}</span>
              <h2>{displayName}</h2>
              <div className="dash-dataset-meta">
                <code>{datasetId}</code>
                {imageCount != null && (
                  <span>{t("home.imageCount", { count: imageCount, defaultValue: "{{count}} images" })}</span>
                )}
                {activeDataset?.status && (
                  <span className="dash-status-chip">{activeDataset.status}</span>
                )}
              </div>
            </div>
            <div className="dash-dataset-actions">
              <button type="button" className="btn btn-primary" onClick={() => onNavigate("annotate")}>
                {t("home.startAnnotation")}
              </button>
              <button type="button" className="btn btn-accent-green" onClick={() => onNavigate("liveAnnotate")}>
                {t("nav.liveAnnotate")}
              </button>
              <button type="button" className="btn" onClick={() => onNavigate("upload")}>
                {t("home.uploadImages")}
              </button>
              <button type="button" className="btn" onClick={() => onNavigate("segment")}>
                {t("home.roadSegmentation")}
              </button>
              <button type="button" className="btn" onClick={() => onNavigate("training")}>
                {t("home.trainModel")}
              </button>
            </div>
          </section>

          {showDashboardHealth && healthError && (
            <ErrorState title={t("home.healthFailed")} body={t("health.emptyBody", "Metrics are not available yet.")} />
          )}

          {showDashboardHealth && health && (
            <section className="dash-panel dash-panel--health">
              <div className="dash-panel-header">
                <h3>{t("home.datasetHealth")}</h3>
                <span className={`dash-score-badge dash-score-badge--${overallTone}`}>
                  {health.overall_score.toFixed(0)}% {t("home.overall")}
                </span>
              </div>
              <div className="dash-metrics-grid">
                <HealthMetric label={t("home.overall")} value={health.overall_score} accent="var(--accent-blue)" />
                <HealthMetric label={t("home.complete")} value={health.completeness_pct} accent="var(--accent-green)" />
                <HealthMetric label={t("home.accuracy")} value={health.accuracy_pct} accent="var(--accent-purple)" />
                <HealthMetric label={t("home.consistent")} value={health.consistency_pct} accent="var(--accent-yellow)" />
              </div>
              {health.recommendations.length > 0 && (
                <ul className="dash-recommendations">
                  {health.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <section className="dash-panel">
            <div className="dash-panel-header">
              <h3>{t("home.quickActions")}</h3>
              <p>{t("home.quickActionsHint", "Jump into a workflow — grouped by task type.")}</p>
            </div>
            <div className="dash-workflows">
              {WORKFLOW_GROUPS.map((group) => (
                <div key={group.sectionKey} className={`dash-workflow-group ${WORKFLOW_GROUP_CLASS[group.sectionKey] ?? ""}`}>
                  <div className="dash-workflow-heading">
                    {t(group.sectionKey)}
                  </div>
                  <div className="dash-action-grid">
                    {group.actions.map(({ v, labelKey, color, path }) => (
                      <button
                        key={v}
                        type="button"
                        className="dash-action-card"
                        style={toStyle({ "--action-accent": color })}
                        onClick={() => onNavigate(v)}
                      >
                        <span className="dash-action-icon">
                          <ActionIcon path={path} color={color} />
                        </span>
                        <span>{t(labelKey)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
