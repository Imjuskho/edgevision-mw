import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Database, Plus, RotateCcw } from "lucide-react";
import type { Dataset } from "../types";
import { DatasetQualityPanel } from "../components/DatasetQualityPanel";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  Modal,
  SearchInput,
  Select,
  SkeletonCard,
  Toolbar,
} from "../components/ui";
import { buildPath } from "../routes/paths";
import { getLastDatasetId, setLastDatasetId } from "../utils/datasetContext";
import { slugifyDatasetId } from "../utils/annotateLabels";
import { useAuth } from "../hooks/useAuth";
import { canManageOperationalSettings } from "../utils/roles";
import { studioApi } from "../services/api";
import { useToast } from "../components/Toast";

const TYPE_BADGE_KEYS: Record<string, { labelKey: string; variant: "info" | "success" | "warning" | "default" }> = {
  sync: { labelKey: "datasets.typeSync", variant: "info" },
  photo: { labelKey: "datasets.typePhoto", variant: "success" },
  studio: { labelKey: "datasets.typeStudio", variant: "default" },
  phase: { labelKey: "datasets.typePhase", variant: "warning" },
};

const SORT_OPTIONS = [
  { value: "created_at", labelKey: "datasets.sortDate" },
  { value: "name", labelKey: "datasets.sortName" },
  { value: "sample_count", labelKey: "datasets.sortCount" },
] as const;

const STATUS_FILTERS = [
  { value: "all", labelKey: "datasets.filterAll" },
  { value: "READY", labelKey: "datasets.filterReady" },
  { value: "BUILDING", labelKey: "datasets.filterBuilding" },
  { value: "FOR_SALE", labelKey: "datasets.filterDraft" },
] as const;

const SOURCE_TYPE_OPTIONS = [
  { value: "studio", labelKey: "datasets.typeStudio" },
  { value: "photo", labelKey: "datasets.typePhoto" },
  { value: "sync", labelKey: "datasets.typeSync" },
  { value: "phase", labelKey: "datasets.typePhase" },
] as const;

interface DatasetBrowserProps {
  datasets: Dataset[];
  loading: boolean;
  error?: boolean;
  selectedId: string;
  onSelect: (id: string) => void;
  onRefresh: (params?: { search?: string; status?: string }) => void;
  onLoadMore: () => void;
  hasMore: boolean;
  totalCount: number;
  currentPage: number;
}

function formatDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale.startsWith("ny") ? "ny-MW" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatRelative(value: string, locale: string) {
  const rtf = new Intl.RelativeTimeFormat(locale.startsWith("ny") ? "ny-MW" : "en", { numeric: "auto" });
  const diffMs = Date.now() - new Date(value).getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (Math.abs(diffDays) >= 1) return rtf.format(-diffDays, "day");
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));
  if (Math.abs(diffHours) >= 1) return rtf.format(-diffHours, "hour");
  const diffMinutes = Math.round(diffMs / (1000 * 60));
  return rtf.format(-diffMinutes, "minute");
}

function normalizeType(value: string | undefined) {
  if (!value) return "studio";
  const normalized = value.toLowerCase();
  if (normalized.includes("sync")) return "sync";
  if (normalized.includes("photo")) return "photo";
  if (normalized.includes("phase")) return "phase";
  return "studio";
}

function healthVariant(score: number | undefined): "success" | "warning" | "danger" | "default" {
  if (!score) return "default";
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "danger";
}

function healthLabel(
  score: number | undefined,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  if (!score) return t("datasets.noIaa");
  const pct = Math.round(score * 100);
  if (pct >= 80) return t("datasets.healthGood", { score: pct });
  if (pct >= 50) return t("datasets.healthFair", { score: pct });
  return t("datasets.healthLow", { score: pct });
}

export default function DatasetBrowser({
  datasets,
  loading,
  error = false,
  selectedId,
  onSelect,
  onRefresh,
  onLoadMore,
  hasMore,
  totalCount,
  currentPage,
}: DatasetBrowserProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { showToast } = useToast();
  const canCreate = canManageOperationalSettings(user?.role);

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("created_at");
  const [filterType, setFilterType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createId, setCreateId] = useState("");
  const [createSourceType, setCreateSourceType] = useState("studio");
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Dataset | null>(null);

  const lastDatasetId = getLastDatasetId();
  const resumeDataset = datasets.find((d) => (d.dataset_id || d.id) === lastDatasetId);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      onRefresh({
        search: search.trim() || undefined,
        status: statusFilter === "all" ? undefined : statusFilter,
      });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search, statusFilter, onRefresh]);

  const filteredDatasets = useMemo(() => {
    return datasets
      .map((ds) => ({ ...ds, dataset_type: normalizeType(ds.dataset_type) }))
      .filter((ds) => filterType === "all" || ds.dataset_type === filterType)
      .sort((a, b) => {
        if (sortKey === "name") return (a.name || "").localeCompare(b.name || "");
        if (sortKey === "sample_count") return (b.sample_count || 0) - (a.sample_count || 0);
        const aTime = new Date(a.updated_at || a.created_at).getTime();
        const bTime = new Date(b.updated_at || b.created_at).getTime();
        return bTime - aTime;
      });
  }, [datasets, filterType, sortKey]);

  const handleCreate = async () => {
    const id = createId.trim() || slugifyDatasetId(createName);
    if (!id || !createName.trim()) return;
    setCreating(true);
    try {
      await studioApi.createDataset({
        name: createName.trim(),
        dataset_id: id,
        source_type: createSourceType,
      });
      setLastDatasetId(id);
      setCreateOpen(false);
      setCreateName("");
      setCreateId("");
      showToast(t("datasets.createSuccess"), "success");
      onRefresh({ search, status: statusFilter === "all" ? undefined : statusFilter });
      navigate(buildPath("upload", { datasetId: id }));
    } catch {
      setLastDatasetId(id);
      setCreateOpen(false);
      showToast(t("datasets.createFallback"), "info");
      navigate(buildPath("upload", { datasetId: id }));
    } finally {
      setCreating(false);
    }
  };

  const refreshFilters = {
    search: search.trim() || undefined,
    status: statusFilter === "all" ? undefined : statusFilter,
  };

  return (
    <div className="page-shell dataset-browser-page">
      <div className="dataset-header page-accent-header page-accent--data">
        <div className="page-accent-header-text">
          <p className="page-label">{t("datasets.pageLabel")}</p>
          <h1>{t("datasets.heading")}</h1>
          <p>{t("datasets.subtitle")}</p>
        </div>

        <Toolbar
          count={totalCount}
          countLabel={t("datasets.found", { count: totalCount })}
          search={
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={t("datasets.searchPlaceholder")}
              aria-label={t("datasets.searchAria")}
              className="dataset-search"
            />
          }
          filters={
            <Select
              value={sortKey}
              options={SORT_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
              onChange={setSortKey}
              aria-label={t("datasets.sortBy")}
            />
          }
          actions={
            <>
              <Button variant="secondary" size="sm" onClick={() => onRefresh(refreshFilters)} disabled={loading}>
                {loading ? t("datasets.refreshing") : t("datasets.refresh")}
              </Button>
              {canCreate && (
                <Button variant="primary" size="sm" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
                  {t("datasets.create")}
                </Button>
              )}
            </>
          }
        />

        <div className="filter-chip-row">
          {Object.entries(TYPE_BADGE_KEYS).map(([key, badge]) => (
            <button
              key={key}
              type="button"
              className={`filter-chip ${filterType === key ? "active" : ""}`}
              onClick={() => setFilterType(filterType === key ? "all" : key)}
            >
              {t(badge.labelKey)}
            </button>
          ))}
        </div>

        <div className="filter-chip-row">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className={`filter-chip ${statusFilter === f.value ? "active" : ""}`}
              onClick={() => setStatusFilter(f.value)}
            >
              {t(f.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {resumeDataset && (
        <div className="dataset-resume-banner">
          <div>
            <strong>{t("datasets.resumeTitle")}</strong>
            <p className="text-body-sm">{resumeDataset.name || resumeDataset.dataset_id}</p>
          </div>
          <Button
            variant="primary"
            size="sm"
            icon={<RotateCcw size={14} />}
            onClick={() => onSelect(resumeDataset.dataset_id || resumeDataset.id)}
          >
            {t("datasets.continueLabeling")}
          </Button>
        </div>
      )}

      <div className="dataset-summary-row">
        <span>{t("datasets.page", { page: currentPage })}</span>
      </div>

      {error && !loading ? (
        <ErrorState
          title={t("datasets.errorTitle")}
          body={t("datasets.errorBody")}
          onRetry={() => onRefresh(refreshFilters)}
          retryLabel={t("datasets.retry")}
        />
      ) : loading && datasets.length === 0 ? (
        <div className="dataset-loading-grid">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      ) : filteredDatasets.length === 0 ? (
        <EmptyState
          icon={<Database size={36} />}
          title={t("datasets.emptyTitle")}
          body={t("datasets.emptyBody")}
          action={
            canCreate ? (
              <Button variant="primary" onClick={() => setCreateOpen(true)}>
                {t("datasets.create")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="dataset-grid">
          {filteredDatasets.map((ds) => {
            const id = ds.dataset_id || ds.id;
            const type = normalizeType(ds.dataset_type);
            const badge = TYPE_BADGE_KEYS[type] || TYPE_BADGE_KEYS.studio;
            const lastActivity = ds.updated_at || ds.created_at;
            const isResume = id === lastDatasetId;
            return (
              <div key={id} className={`dataset-card-wrap${selectedId === id ? " selected" : ""}`}>
                <button className="dataset-card" onClick={() => onSelect(id)} type="button">
                  <div className="card-header-row">
                    <Badge variant={badge.variant}>{t(badge.labelKey)}</Badge>
                    <Badge variant={healthVariant(ds.iaa_score)}>
                      {healthLabel(ds.iaa_score, t)}
                    </Badge>
                  </div>
                  <div className="ds-name" title={ds.name}>{ds.name || id}</div>
                  <DatasetQualityPanel
                    iaaScore={ds.iaa_score}
                    piiScrubVerified={ds.pii_scrub_verified}
                    consentCoveragePct={ds.consent_coverage_pct}
                    sampleCount={ds.sample_count}
                    classes={ds.classes}
                    status={ds.status}
                  />
                  <div className="ds-meta-row">
                    <span>{ds.sample_count?.toLocaleString()} {t("datasets.images")}</span>
                    <span title={formatDate(lastActivity, i18n.language)}>
                      {t("datasets.lastActivity", { when: formatRelative(lastActivity, i18n.language) })}
                    </span>
                  </div>
                  <div className="ds-bottom-row">
                    <span className="ds-id text-mono">{id}</span>
                    <Badge variant="default">{ds.status || t("datasets.unknownStatus")}</Badge>
                  </div>
                  {isResume && (
                    <Badge variant="info" className="dataset-card-resume-badge">
                      {t("datasets.continueLabeling")}
                    </Badge>
                  )}
                </button>
                {canCreate && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="dataset-card-delete"
                    onClick={() => setDeleteTarget(ds)}
                  >
                    {t("datasets.delete")}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {hasMore && !loading && !error && (
        <div className="dataset-load-more">
          <Button variant="primary" onClick={onLoadMore}>
            {t("datasets.loadMore")}
          </Button>
        </div>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("datasets.createTitle")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" onClick={() => void handleCreate()} loading={creating} disabled={!createName.trim()}>
              {t("datasets.createAndUpload")}
            </Button>
          </>
        }
      >
        <FormField label={t("datasets.createName")} htmlFor="ds-create-name">
          <Input
            id="ds-create-name"
            value={createName}
            onChange={(e) => {
              setCreateName(e.target.value);
              if (!createId) setCreateId(slugifyDatasetId(e.target.value));
            }}
            placeholder={t("datasets.createNamePlaceholder")}
          />
        </FormField>
        <FormField
          label={t("datasets.createId")}
          hint={t("datasets.createIdHint")}
          htmlFor="ds-create-id"
        >
          <Input
            id="ds-create-id"
            value={createId}
            onChange={(e) => setCreateId(slugifyDatasetId(e.target.value))}
            className="text-mono"
          />
        </FormField>
        <FormField label={t("datasets.createSourceType")} htmlFor="ds-create-source">
          <Select
            value={createSourceType}
            options={SOURCE_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
            onChange={setCreateSourceType}
            aria-label={t("datasets.createSourceType")}
          />
        </FormField>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("datasets.deleteTitle")}
        message={t("datasets.deleteUnavailable")}
        confirmLabel={t("common.ok")}
        cancelLabel={t("common.cancel")}
        onConfirm={() => setDeleteTarget(null)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
