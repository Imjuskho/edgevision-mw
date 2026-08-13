import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { studioApi } from "../services/api";

interface AuditItem {
  id: string;
  event_type: string;
  severity: string;
  actor_email: string | null;
  resource_type: string;
  resource_id: string | null;
  created_at: string | null;
  details: Record<string, unknown> | null;
}

const FILTER_OPTIONS = [
  "",
  "settings.operational_updated",
  "review.job_certified",
  "review.job_rejected",
  "review.annotation_approved",
  "review.annotation_rejected",
];

export function AuditLogPanel() {
  const { t } = useTranslation();
  const [items, setItems] = useState<AuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await studioApi.listAuditLogs({
        event_type: eventFilter || undefined,
        limit,
        offset,
      });
      setItems(resp.data.items ?? []);
      setTotal(resp.data.total ?? 0);
    } catch {
      setError(t("audit.loadFailed", "Could not load audit log."));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [eventFilter, offset, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="settings-panel audit-log-panel">
      <h2>{t("audit.title", "Audit log")}</h2>
      <p className="settings-panel-desc">
        {t("audit.desc", "Settings changes, QA certifications, and review decisions.")}
      </p>

      <div className="audit-log-toolbar">
        <select
          className="settings-select"
          value={eventFilter}
          onChange={(e) => {
            setOffset(0);
            setEventFilter(e.target.value);
          }}
          aria-label={t("audit.filterLabel", "Filter by event type")}
        >
          <option value="">{t("audit.allEvents", "All events")}</option>
          {FILTER_OPTIONS.filter(Boolean).map((ev) => (
            <option key={ev} value={ev}>
              {t(`audit.events.${ev}`, ev)}
            </option>
          ))}
        </select>
        <button type="button" className="btn btn-sm" onClick={() => void load()} disabled={loading}>
          {t("audit.refresh", "Refresh")}
        </button>
      </div>

      {error && <p className="analysis-error">{error}</p>}
      {loading && <p className="text-secondary">{t("audit.loading", "Loading…")}</p>}

      {!loading && items.length === 0 && !error && (
        <p className="text-secondary">{t("audit.empty", "No audit entries yet.")}</p>
      )}

      {!loading && items.length > 0 && (
        <ul className="audit-log-list">
          {items.map((item) => (
            <li key={item.id} className={`audit-log-row audit-log-row--${item.severity.toLowerCase()}`}>
              <div className="audit-log-row-head">
                <span className="audit-log-event">{t(`audit.events.${item.event_type}`, item.event_type)}</span>
                <time className="audit-log-time">
                  {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
                </time>
              </div>
              <div className="audit-log-row-meta">
                {item.actor_email && (
                  <span>{t("audit.by", "By")}: {item.actor_email}</span>
                )}
                {item.resource_type && (
                  <span>
                    {item.resource_type}
                    {item.resource_id ? ` · ${item.resource_id.slice(0, 8)}…` : ""}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {total > limit && (
        <div className="audit-log-pagination">
          <button
            type="button"
            className="btn btn-sm"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            {t("audit.prev", "Previous")}
          </button>
          <span className="text-secondary text-sm">
            {offset + 1}–{Math.min(offset + limit, total)} / {total}
          </span>
          <button
            type="button"
            className="btn btn-sm"
            disabled={offset + limit >= total || loading}
            onClick={() => setOffset(offset + limit)}
          >
            {t("audit.next", "Next")}
          </button>
        </div>
      )}
    </section>
  );
}
