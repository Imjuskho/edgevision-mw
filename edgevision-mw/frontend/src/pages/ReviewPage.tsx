import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Check, ChevronLeft, X } from "lucide-react";
import { ReviewImagePreview } from "../components/ReviewImagePreview";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { PageShell } from "../components/PageShell";
import { useToast } from "../components/Toast";
import { useStudioSettings } from "../context/StudioSettingsContext";
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  IconButton,
  Skeleton,
  StatCard,
} from "../components/ui";
import type { BadgeVariant } from "../components/ui/Badge";
import type { DataTableColumn } from "../components/ui/DataTable";

interface ReviewItem {
  assignment_id: string;
  dataset_id: string;
  dataset_name: string;
  annotator_name: string;
  total_images: number;
  completed_images: number;
  submitted_at: string | null;
  deadline: string | null;
  priority: number;
  status?: string;
}

interface ReviewDetail {
  assignment_id: string;
  dataset_id: string;
  dataset_name: string;
  annotator_name: string;
  total_images: number;
  completed_images: number;
  images: {
    id: string;
    image_path: string;
    index: number;
    status: string;
    is_certified: boolean;
    annotations: { label: string; x: number; y: number; width: number; height: number; confidence: number }[];
    has_human_labels: boolean;
  }[];
  deadline: string | null;
  priority: number;
}

interface IAAMetrics {
  total_annotations: number;
  annotations_with_labels: number;
  annotations_certified: number;
  annotations_rejected: number;
  completeness_pct: number;
  accuracy_pct: number;
  overall_iaa: number;
}

type JobDialog = "certify" | "reject" | null;

interface Props {
  assignmentId?: string;
  onBack?: () => void;
}

function scoreTone(score: number): "good" | "fair" | "low" {
  if (score >= 75) return "good";
  if (score >= 45) return "fair";
  return "low";
}

function reviewStatusVariant(status?: string): BadgeVariant {
  const s = (status || "SUBMITTED").toUpperCase();
  if (s === "CERTIFIED") return "success";
  if (s === "REJECTED" || s === "ASSIGNED") return "danger";
  return "warning";
}

export default function ReviewPage({ assignmentId, onBack: _onBack }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { expertMode } = useStudioSettings();
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [selected, setSelected] = useState<ReviewDetail | null>(null);
  const [iaa, setIaa] = useState<IAAMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [imageIdx, setImageIdx] = useState(0);
  const [message, setMessage] = useState("");
  const [jobDialog, setJobDialog] = useState<JobDialog>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [jobBusy, setJobBusy] = useState(false);
  const [annotationBusyId, setAnnotationBusyId] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState("submitted_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const reviewStatusLabel = (status?: string) => {
    const key = status?.toLowerCase() || "submitted";
    return t(`review.status.${key}`, status || "SUBMITTED");
  };

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch("/api/v1/review/queue", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error("Failed to load review queue");
      const data = await resp.json();
      setItems(data.items || []);
    } catch (err) {
      setLoadError(true);
      setMessage(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const token = localStorage.getItem("studio_token");
      const [detailResp, iaaResp] = await Promise.all([
        fetch(`/api/v1/review/jobs/${id}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`/api/v1/review/jobs/${id}/iaa`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (detailResp.ok) setSelected(await detailResp.json());
      if (iaaResp.ok) setIaa(await iaaResp.json());
      setImageIdx(0);
    } catch (err) {
      setMessage(String(err));
    }
  }, []);

  useEffect(() => { void loadQueue(); }, [loadQueue]);
  useEffect(() => { if (assignmentId) void loadDetail(assignmentId); }, [assignmentId, loadDetail]);

  const sortedItems = useMemo(() => {
    const list = [...items];
    list.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "dataset_name") cmp = a.dataset_name.localeCompare(b.dataset_name);
      else if (sortKey === "progress") cmp = a.completed_images / a.total_images - b.completed_images / b.total_images;
      else if (sortKey === "status") cmp = (a.status || "").localeCompare(b.status || "");
      else {
        const aDate = a.submitted_at || a.deadline || "";
        const bDate = b.submitted_at || b.deadline || "";
        cmp = aDate.localeCompare(bDate);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [items, sortKey, sortDir]);

  const handleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const queueColumns: DataTableColumn<ReviewItem>[] = [
    {
      key: "dataset_name",
      header: t("reviewQueue.dataset", "Dataset"),
      sortable: true,
      render: (item) => (
        <div>
          <div className="review-queue-cell-title">{item.dataset_name}</div>
          <div className="review-queue-cell-sub">{item.annotator_name}</div>
        </div>
      ),
    },
    {
      key: "progress",
      header: t("reviewQueue.progress", "Progress"),
      sortable: true,
      render: (item) => (
        <span className="review-queue-progress">
          {item.completed_images}/{item.total_images}
        </span>
      ),
    },
    {
      key: "status",
      header: t("reviewQueue.status", "Status"),
      sortable: true,
      render: (item) => <Badge variant={reviewStatusVariant(item.status)}>{reviewStatusLabel(item.status)}</Badge>,
    },
    {
      key: "submitted_at",
      header: t("reviewQueue.date", "Date"),
      sortable: true,
      render: (item) => {
        const date = item.submitted_at || item.deadline;
        return date ? (
          <span className="review-queue-date">{new Date(date).toLocaleDateString()}</span>
        ) : (
          <span className="review-queue-date">—</span>
        );
      },
    },
  ];

  const openRejectDialog = () => {
    setRejectReason("");
    setJobDialog("reject");
  };

  const closeJobDialog = () => {
    if (jobBusy) return;
    setJobDialog(null);
    setRejectReason("");
  };

  const certifyJob = async () => {
    if (!selected) return;
    setJobBusy(true);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch(`/api/v1/review/jobs/${selected.assignment_id}/certify`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(t("reviewDetail.actionFailed"));
      setMessage(t("reviewDetail.certified"));
      showToast(t("reviewDetail.certified"), "success");
      setSelected(null);
      setJobDialog(null);
      void loadQueue();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("reviewDetail.actionFailed");
      showToast(msg, "error");
    } finally {
      setJobBusy(false);
    }
  };

  const rejectJob = async () => {
    if (!selected) return;
    const reason = rejectReason.trim();
    if (!reason) {
      showToast(t("reviewDetail.rejectReasonRequired"), "error");
      return;
    }
    setJobBusy(true);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch(`/api/v1/review/jobs/${selected.assignment_id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ decision: "reject", reason }),
      });
      if (!resp.ok) throw new Error(t("reviewDetail.actionFailed"));
      setMessage(t("reviewDetail.rejectedMsg"));
      showToast(t("reviewDetail.rejectedMsg"), "success");
      setSelected(null);
      setJobDialog(null);
      setRejectReason("");
      void loadQueue();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("reviewDetail.actionFailed");
      showToast(msg, "error");
    } finally {
      setJobBusy(false);
    }
  };

  const approveAnnotation = async (assignmentId: string, annotationId: string) => {
    setAnnotationBusyId(annotationId);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch(`/api/v1/review/jobs/${assignmentId}/annotations/${annotationId}/approve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(t("reviewDetail.actionFailed"));
      showToast(t("reviewDetail.annotationApproved"), "success");
      await loadDetail(assignmentId);
    } catch (err) {
      showToast(err instanceof Error ? err.message : t("reviewDetail.actionFailed"), "error");
    } finally {
      setAnnotationBusyId(null);
    }
  };

  const rejectAnnotation = async (assignmentId: string, annotationId: string) => {
    setAnnotationBusyId(annotationId);
    try {
      const token = localStorage.getItem("studio_token");
      const resp = await fetch(`/api/v1/review/jobs/${assignmentId}/annotations/${annotationId}/reject`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(t("reviewDetail.actionFailed"));
      showToast(t("reviewDetail.annotationRejected"), "success");
      await loadDetail(assignmentId);
    } catch (err) {
      showToast(err instanceof Error ? err.message : t("reviewDetail.actionFailed"), "error");
    } finally {
      setAnnotationBusyId(null);
    }
  };

  const currentImage = selected?.images[imageIdx];
  const imageBusy = currentImage ? annotationBusyId === currentImage.id : false;

  const jobConfirmDialog = selected && jobDialog ? (
    <ConfirmDialog
      open
      title={
        jobDialog === "certify"
          ? t("reviewDetail.confirmCertifyTitle")
          : t("reviewDetail.confirmRejectTitle")
      }
      message={
        jobDialog === "certify"
          ? t("reviewDetail.confirmCertifyMessage", {
              dataset: selected.dataset_name,
              annotator: selected.annotator_name,
              count: selected.completed_images,
            })
          : t("reviewDetail.confirmRejectMessage", {
              dataset: selected.dataset_name,
              annotator: selected.annotator_name,
            })
      }
      confirmLabel={
        jobDialog === "certify" ? t("reviewDetail.certifyAll") : t("reviewDetail.submitReject")
      }
      cancelLabel={t("common.cancel")}
      variant={jobDialog === "reject" ? "danger" : "primary"}
      busy={jobBusy}
      onConfirm={() => void (jobDialog === "certify" ? certifyJob() : rejectJob())}
      onCancel={closeJobDialog}
    >
      {jobDialog === "reject" && (
        <label className="confirm-dialog-field">
          <span>{t("reviewDetail.rejectReason")}</span>
          <textarea
            className="confirm-dialog-textarea"
            rows={3}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder={t("reviewDetail.rejectReasonPlaceholder")}
            disabled={jobBusy}
          />
        </label>
      )}
    </ConfirmDialog>
  ) : null;

  if (selected) {
    return (
      <div className="page-shell review-page">
        <div className="review-detail-shell">
          <div className="review-detail-header">
            <div className="review-detail-header-row">
              <Button
                variant="secondary"
                size="sm"
                icon={<ChevronLeft size={14} />}
                onClick={() => { setSelected(null); setIaa(null); }}
              >
                {t("reviewDetail.back", "Back")}
              </Button>
              <div>
                <div className="review-detail-title">{selected.dataset_name}</div>
                <div className="review-detail-subtitle">
                  {t("reviewQueue.annotator", "by")} {selected.annotator_name}
                </div>
              </div>
            </div>

            <div className="review-detail-actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/datasets/${selected.dataset_id}/review/fast`)}
              >
                {t("reviewDetail.fastReview")}
              </Button>
              {iaa && (
                <div className="review-iaa-stats">
                  <StatCard
                    label={t("review.completeness", "Complete")}
                    value={`${iaa.completeness_pct}%`}
                    className={`ui-stat-card--${scoreTone(iaa.completeness_pct)}`}
                  />
                  <StatCard
                    label={t("review.accuracy", "Accuracy")}
                    value={`${iaa.accuracy_pct}%`}
                    className={`ui-stat-card--${scoreTone(iaa.accuracy_pct)}`}
                  />
                  <StatCard
                    label={t("review.iaa", "IAA")}
                    value={`${iaa.overall_iaa}%`}
                    className={`ui-stat-card--${scoreTone(iaa.overall_iaa)}`}
                  />
                </div>
              )}
              {!expertMode && (
                <p className="dedup-expert-hint">{t("review.expertBatchHint")}</p>
              )}
              {expertMode && (
                <div className="review-expert-actions">
                  <Button variant="primary" onClick={() => setJobDialog("certify")}>
                    {t("reviewDetail.certifyAll", "Certify All")}
                  </Button>
                  <Button variant="danger" onClick={openRejectDialog}>
                    {t("reviewDetail.rejectAll", "Reject All")}
                  </Button>
                </div>
              )}
            </div>
          </div>

          <div className="review-detail-main">
            <div className="review-filmstrip">
              {selected.images.map((img, idx) => (
                <div
                  key={img.id}
                  className={`review-filmstrip-item${idx === imageIdx ? " active" : ""}`}
                  onClick={() => setImageIdx(idx)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter") setImageIdx(idx); }}
                >
                  <div className="review-filmstrip-index">#{img.index}</div>
                  <div className="review-filmstrip-meta">
                    {img.annotations.length} {t("review.labels", "labels")}
                  </div>
                  {img.is_certified && <Check size={12} className="review-filmstrip-certified" />}
                </div>
              ))}
            </div>

            <div className="review-detail-panel">
              {currentImage ? (
                <>
                  <div className="review-image-meta">
                    {t("review.image", "Image")} #{currentImage.index} — {currentImage.annotations.length}{" "}
                    {t("review.annotations", "annotations")}
                  </div>

                  <ReviewImagePreview
                    annotationId={currentImage.id}
                    annotations={currentImage.annotations}
                  />

                  <div className="review-annotations">
                    {currentImage.annotations.map((ann, idx) => (
                      <div key={idx} className="review-annotation-row">
                        <span className="review-annotation-label">{ann.label}</span>
                        <span className="review-annotation-confidence">{ann.confidence.toFixed(2)}</span>
                        <span className="review-annotation-coords">
                          [{ann.x.toFixed(2)}, {ann.y.toFixed(2)}, {ann.width.toFixed(2)}, {ann.height.toFixed(2)}]
                        </span>
                        <div className="review-annotation-actions">
                          <IconButton
                            label={t("reviewDetail.approve")}
                            size="sm"
                            disabled={imageBusy}
                            onClick={() => void approveAnnotation(selected.assignment_id, currentImage.id)}
                          >
                            <Check size={14} />
                          </IconButton>
                          <IconButton
                            label={t("reviewDetail.reject")}
                            size="sm"
                            disabled={imageBusy}
                            onClick={() => void rejectAnnotation(selected.assignment_id, currentImage.id)}
                          >
                            <X size={14} />
                          </IconButton>
                        </div>
                      </div>
                    ))}
                    {currentImage.annotations.length === 0 && (
                      <EmptyState
                        title={t("reviewDetail.noAnnotations", "No annotations on this image")}
                        className="review-empty-annotations"
                      />
                    )}
                  </div>

                  <div className="review-nav">
                    <Button size="sm" variant="secondary" onClick={() => setImageIdx(Math.max(0, imageIdx - 1))} disabled={imageIdx === 0}>
                      ← {t("review.prev", "Previous")}
                    </Button>
                    <span className="review-nav-index">
                      {imageIdx + 1} / {selected.images.length}
                    </span>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setImageIdx(Math.min(selected.images.length - 1, imageIdx + 1))}
                      disabled={imageIdx >= selected.images.length - 1}
                    >
                      {t("review.next", "Next")} →
                    </Button>
                  </div>
                </>
              ) : (
                <EmptyState
                  title={t("review.selectImage", "Select an image from the sidebar")}
                  className="review-empty-panel"
                />
              )}
            </div>
          </div>

          {message && <div className="review-message">{message}</div>}
        </div>
        {jobConfirmDialog}
      </div>
    );
  }

  return (
    <PageShell
      accent="quality"
      title={t("reviewQueue.title", "QA Review Queue")}
      subtitle={t("review.subtitle", "Review submitted annotation batches and certify quality.")}
    >
      {message && <div className="review-message">{message}</div>}

      {loading ? (
        <Skeleton className="review-queue-skeleton" />
      ) : loadError ? (
        <ErrorState
          title={t("review.loadFailed", "Failed to load review queue")}
          body={message}
          onRetry={() => void loadQueue()}
          retryLabel={t("datasets.retry", "Retry")}
        />
      ) : (
        <DataTable
          columns={queueColumns}
          data={sortedItems}
          rowKey={(item) => item.assignment_id}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={handleSort}
          onRowClick={(item) => void loadDetail(item.assignment_id)}
          stickyHeader
          emptyTitle={t("reviewQueue.noJobs", "No jobs awaiting review.")}
        />
      )}
    </PageShell>
  );
}
