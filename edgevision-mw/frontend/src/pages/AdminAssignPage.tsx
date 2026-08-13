import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { studioApi } from "../services/api";
import { useToast } from "../components/Toast";
import {
  Badge,
  Button,
  Checkbox,
  DataTable,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  Modal,
  ProgressBar,
} from "../components/ui";
import type { BadgeVariant } from "../components/ui/Badge";
import type { DataTableColumn } from "../components/ui/DataTable";

interface Assignment {
  id: string;
  dataset_id: string;
  dataset_name: string;
  annotator_id: string;
  annotator_name: string;
  status: string;
  deadline: string | null;
  priority: number;
  total_images: number;
  completed_images: number;
  progress_pct: number;
  is_overdue: boolean;
  created_at: string;
}

interface AnnotatorUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

interface Props {
  onNavigate?: (view: string, datasetId?: string) => void;
}

function assignStatusVariant(status: string): BadgeVariant {
  if (status === "CERTIFIED") return "success";
  if (status === "SUBMITTED") return "warning";
  if (status === "ASSIGNED") return "info";
  return "default";
}

function rowAccentClass(status: string, overdue: boolean): string {
  if (overdue) return "admin-row-accent--overdue";
  const s = status.toUpperCase();
  if (s === "CERTIFIED") return "admin-row-accent--certified";
  if (s === "SUBMITTED") return "admin-row-accent--submitted";
  if (s === "ASSIGNED") return "admin-row-accent--assigned";
  return "admin-row-accent--default";
}

export default function AdminAssignPage({ onNavigate: _onNavigate }: Props) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [datasetId, setDatasetId] = useState("");
  const [selectedAnnotators, setSelectedAnnotators] = useState<string[]>([]);
  const [annotators, setAnnotators] = useState<AnnotatorUser[]>([]);
  const [annotatorsLoading, setAnnotatorsLoading] = useState(false);
  const [annotatorsError, setAnnotatorsError] = useState(false);
  const [deadline, setDeadline] = useState("");
  const [priority, setPriority] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [sortKey, setSortKey] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const resp = await studioApi.listAssignments();
      const items = resp.data?.items || resp.data;
      setAssignments(Array.isArray(items) ? items : []);
    } catch {
      setLoadError(true);
      showToast(t("errors.networkError"), "error");
    } finally {
      setLoading(false);
    }
  }, [showToast, t]);

  const loadAnnotators = useCallback(async () => {
    setAnnotatorsLoading(true);
    setAnnotatorsError(false);
    try {
      const resp = await studioApi.listUsers({ role: "ANNOTATOR" });
      setAnnotators(resp.data ?? []);
    } catch {
      setAnnotators([]);
      setAnnotatorsError(true);
    } finally {
      setAnnotatorsLoading(false);
    }
  }, []);

  useEffect(() => { void loadAssignments(); }, [loadAssignments]);
  useEffect(() => {
    if (createOpen) void loadAnnotators();
  }, [createOpen, loadAnnotators]);

  const toggleAnnotator = (id: string) => {
    setSelectedAnnotators((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const createAssignment = async () => {
    if (!datasetId.trim() || selectedAnnotators.length === 0) return;
    setSubmitting(true);
    try {
      await studioApi.createAssignment(
        datasetId.trim(),
        selectedAnnotators,
        deadline || undefined,
        String(priority),
      );
      showToast(t("admin.assignSuccess"), "success");
      setCreateOpen(false);
      setDatasetId("");
      setSelectedAnnotators([]);
      setDeadline("");
      setPriority(5);
      void loadAssignments();
    } catch {
      showToast(t("admin.assignFailed"), "error");
    } finally {
      setSubmitting(false);
    }
  };

  const filteredAssignments = useMemo(() => {
    let list = assignments.filter((a) => {
      if (overdueOnly && !a.is_overdue) return false;
      if (statusFilter !== "all" && a.status !== statusFilter) return false;
      return true;
    });
    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "dataset_name") cmp = a.dataset_name.localeCompare(b.dataset_name);
      else if (sortKey === "progress") cmp = a.progress_pct - b.progress_pct;
      else if (sortKey === "priority") cmp = a.priority - b.priority;
      else if (sortKey === "status") cmp = a.status.localeCompare(b.status);
      else cmp = a.created_at.localeCompare(b.created_at);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [assignments, statusFilter, overdueOnly, sortKey, sortDir]);

  const handleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const columns: DataTableColumn<Assignment>[] = [
    {
      key: "dataset_name",
      header: t("admin.datasetId"),
      sortable: true,
      render: (a) => (
        <div className={rowAccentClass(a.status, a.is_overdue)}>
          <div className="review-queue-cell-title">{a.dataset_name}</div>
          <div className="review-queue-cell-sub">{a.annotator_name}</div>
        </div>
      ),
    },
    {
      key: "progress",
      header: t("queue.progress"),
      sortable: true,
      render: (a) => (
        <div>
          <ProgressBar value={a.progress_pct} aria-label={a.dataset_name} />
          <span className="review-queue-progress">
            {a.completed_images}/{a.total_images} ({a.progress_pct}%)
          </span>
        </div>
      ),
    },
    {
      key: "status",
      header: t("queue.status", "Status"),
      sortable: true,
      render: (a) => <Badge variant={assignStatusVariant(a.status)}>{a.status}</Badge>,
    },
    {
      key: "priority",
      header: t("admin.priority"),
      sortable: true,
      render: (a) => <span className="admin-priority">P{a.priority}</span>,
    },
    {
      key: "deadline",
      header: t("admin.deadline"),
      sortable: true,
      render: (a) =>
        a.deadline ? (
          <span className={`admin-deadline${a.is_overdue ? " admin-deadline--overdue" : ""}`}>
            {new Date(a.deadline).toLocaleDateString()}
          </span>
        ) : (
          <span className="admin-deadline">—</span>
        ),
    },
  ];

  return (
    <div className="page-shell admin-page">
      <div className="page-heading admin-header">
        <h1>{t("admin.title")}</h1>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          {t("admin.newAssignment")}
        </Button>
      </div>

      <div className="data-table-filters">
        {["all", "ASSIGNED", "SUBMITTED", "CERTIFIED"].map((s) => (
          <button
            key={s}
            type="button"
            className={`filter-chip ${statusFilter === s ? "active" : ""}`}
            onClick={() => setStatusFilter(s)}
          >
            {s === "all" ? t("datasets.filterAll", "All") : s}
          </button>
        ))}
        <button
          type="button"
          className={`filter-chip ${overdueOnly ? "active" : ""}`}
          onClick={() => setOverdueOnly((v) => !v)}
        >
          {t("queue.overdueOnly", "Overdue only")}
        </button>
      </div>

      {loadError ? (
        <ErrorState
          title={t("admin.loadFailed", "Failed to load assignments")}
          onRetry={() => void loadAssignments()}
          retryLabel={t("datasets.retry", "Retry")}
        />
      ) : (
        <DataTable
          columns={columns}
          data={filteredAssignments}
          rowKey={(a) => a.id}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={handleSort}
          loading={loading}
          stickyHeader
          emptyTitle={t("admin.empty")}
        />
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("admin.newAssignment")}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="primary"
              onClick={() => void createAssignment()}
              loading={submitting}
              disabled={submitting || !datasetId.trim() || selectedAnnotators.length === 0}
            >
              {submitting ? t("admin.creating") : t("admin.createButton")}
            </Button>
          </>
        }
      >
        <FormField label={t("admin.datasetId")} htmlFor="admin-dataset-id">
          <Input
            id="admin-dataset-id"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            placeholder="DS-LILONGWE-001"
            className="text-mono"
          />
        </FormField>

        <FormField label={t("admin.annotatorPicker")} hint={t("admin.annotatorPickerHelp")}>
          {annotatorsLoading && <p className="text-body-sm">{t("admin.annotatorsLoading")}</p>}
          {annotatorsError && (
            <ErrorState title={t("admin.annotatorsLoadFailed")} />
          )}
          {!annotatorsLoading && !annotatorsError && annotators.length === 0 && (
            <EmptyState title={t("admin.noAnnotators")} />
          )}
          <div className="annotator-picker-list">
            {annotators.map((u) => (
              <label key={u.id} className="annotator-picker-row">
                <Checkbox
                  checked={selectedAnnotators.includes(u.id)}
                  onChange={() => toggleAnnotator(u.id)}
                  label=""
                />
                <span className="annotator-picker-name">{u.full_name || u.email}</span>
                <span className="annotator-picker-email">{u.email}</span>
              </label>
            ))}
          </div>
        </FormField>

        <FormField label={t("admin.deadline")} htmlFor="admin-deadline">
          <Input
            id="admin-deadline"
            type="datetime-local"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </FormField>

        <FormField label={`${t("admin.priority")} (0-10)`} htmlFor="admin-priority">
          <input
            id="admin-priority"
            type="range"
            min="0"
            max="10"
            value={priority}
            aria-valuemin={0}
            aria-valuemax={10}
            aria-valuenow={priority}
            aria-label={t("admin.priority")}
            onChange={(e) => setPriority(Number(e.target.value))}
            className="admin-priority-range"
          />
          <span className="admin-priority-value">{priority}</span>
        </FormField>
      </Modal>
    </div>
  );
}
