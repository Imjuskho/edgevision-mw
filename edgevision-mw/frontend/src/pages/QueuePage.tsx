import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { PageShell } from "../components/PageShell";
import {
  Badge,
  Button,
  DataTable,
  ErrorState,
  ProgressBar,
} from "../components/ui";
import type { BadgeVariant } from "../components/ui/Badge";
import type { DataTableColumn } from "../components/ui/DataTable";

interface QueueItem {
  assignment_id: string;
  dataset_id: string;
  dataset_name: string;
  status: string;
  deadline: string | null;
  priority: number;
  total_images: number;
  completed_images: number;
  progress_pct: number;
  is_overdue: boolean;
  image_count_available: number;
}

interface Props {
  onStartAnnotation: (datasetId: string) => void;
}

function queueStatusVariant(status: string, overdue: boolean): BadgeVariant {
  if (overdue) return "danger";
  if (status === "ASSIGNED") return "info";
  if (status === "IN_PROGRESS") return "warning";
  return "default";
}

async function fetchQueueItems(): Promise<QueueItem[]> {
  const token = localStorage.getItem("studio_token");
  const resp = await fetch("/api/v1/assignments/queue", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error("Failed to load queue");
  const data = await resp.json();
  return data.items || [];
}

export default function QueuePage({ onStartAnnotation }: Props) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [sortKey, setSortKey] = useState("priority");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await fetchQueueItems());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        setItems(await fetchQueueItems());
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const claimJob = async (assignmentId: string) => {
    setActionId(assignmentId);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch("/api/v1/assignments/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ assignment_id: assignmentId }),
      });
      if (!resp.ok) throw new Error("claim failed");
      showToast(t("queue.claimSuccess"), "success");
      await loadQueue();
    } catch {
      showToast(t("queue.claimFailed"), "error");
    } finally {
      setActionId(null);
    }
  };

  const submitJob = async (assignmentId: string) => {
    if (!confirm(t("queue.confirmSubmit"))) return;
    setActionId(assignmentId);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch("/api/v1/assignments/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ assignment_id: assignmentId }),
      });
      if (!resp.ok) throw new Error("submit failed");
      showToast(t("queue.submitSuccess"), "success");
      await loadQueue();
    } catch {
      showToast(t("queue.submitFailed"), "error");
    } finally {
      setActionId(null);
    }
  };

  const filteredItems = useMemo(() => {
    let list = items.filter((item) => {
      if (overdueOnly && !item.is_overdue) return false;
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      return true;
    });
    list = [...list].sort((a, b) => {
      let cmp: number;
      if (sortKey === "dataset_name") cmp = a.dataset_name.localeCompare(b.dataset_name);
      else if (sortKey === "progress") cmp = a.progress_pct - b.progress_pct;
      else if (sortKey === "status") cmp = a.status.localeCompare(b.status);
      else cmp = a.priority - b.priority;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [items, statusFilter, overdueOnly, sortKey, sortDir]);

  const handleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const columns: DataTableColumn<QueueItem>[] = [
    {
      key: "dataset_name",
      header: t("queue.dataset", "Dataset"),
      sortable: true,
      render: (item) => (
        <div>
          <div className="review-queue-cell-title">{item.dataset_name}</div>
          <div className="review-queue-cell-sub text-mono">{item.dataset_id}</div>
        </div>
      ),
    },
    {
      key: "progress",
      header: t("queue.progress"),
      sortable: true,
      render: (item) => (
        <div>
          <ProgressBar value={item.progress_pct} aria-label={item.dataset_name} />
          <span className="review-queue-progress">
            {item.completed_images}/{item.total_images} ({item.progress_pct}%)
          </span>
        </div>
      ),
    },
    {
      key: "status",
      header: t("queue.status", "Status"),
      sortable: true,
      render: (item) => (
        <div>
          <Badge variant={queueStatusVariant(item.status, item.is_overdue)}>{item.status}</Badge>
          {item.is_overdue && <div className="queue-overdue-badge">{t("queue.overdue", "OVERDUE")}</div>}
          {item.deadline && (
            <div className="review-queue-date">{new Date(item.deadline).toLocaleDateString()}</div>
          )}
        </div>
      ),
    },
    {
      key: "priority",
      header: t("queue.priority", "Priority"),
      sortable: true,
      render: (item) => <span className="admin-priority">P{item.priority}</span>,
    },
    {
      key: "actions",
      header: t("queue.actions", "Actions"),
      render: (item) => (
        <div className="queue-table-actions">
          {item.status === "ASSIGNED" && (
            <Button
              variant="primary"
              size="sm"
              disabled={actionId === item.assignment_id}
              loading={actionId === item.assignment_id}
              onClick={(e) => {
                e.stopPropagation();
                void claimJob(item.assignment_id);
              }}
            >
              {t("queue.claim", "Claim")}
            </Button>
          )}
          {(item.status === "ASSIGNED" || item.status === "IN_PROGRESS") && (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onStartAnnotation(item.dataset_id);
                }}
              >
                {t("queue.annotate", "Annotate")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                disabled={actionId === item.assignment_id}
                onClick={(e) => {
                  e.stopPropagation();
                  void submitJob(item.assignment_id);
                }}
              >
                {t("queue.submit", "Submit")}
              </Button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <PageShell
      accent="quality"
      title={t("queue.title", "My Job Queue")}
      subtitle={t("queue.subtitle", "Claim and complete annotation assignments.")}
    >
      <div className="data-table-filters">
        {["all", "ASSIGNED", "IN_PROGRESS"].map((s) => (
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

      {error ? (
        <ErrorState
          title={t("queue.loadFailed", "Failed to load queue")}
          body={error}
          onRetry={() => void loadQueue()}
          retryLabel={t("datasets.retry", "Retry")}
        />
      ) : (
        <DataTable
          columns={columns}
          data={filteredItems}
          rowKey={(item) => item.assignment_id}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={handleSort}
          loading={loading}
          stickyHeader
          emptyTitle={t("queue.noJobs")}
        />
      )}
    </PageShell>
  );
}
