import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import { StatCard, Badge, Button, Spinner, EmptyState, ErrorState } from "../components/ui";
import { useOperatorEvents, type PerceptionEvent } from "../hooks/useOperatorEvents";
import api from "../services/api";

interface OperatorAlert {
  id: string;
  alert_type: string;
  message: string;
  severity: string;
  acknowledged: boolean;
  created_at: string;
}

interface Payout {
  id: string;
  amount_mwk: number;
  status: string;
  created_at: string;
}

interface DashboardData {
  operator_id: string;
  phone: string;
  associated_node_id: string | null;
  total_earnings_mwk: number;
  total_annotations: number;
  pending_alerts: number;
  recent_alerts: OperatorAlert[];
  payout_history: Payout[];
}

function humanizeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function severityVariant(s: string): "info" | "warning" | "danger" {
  switch (s?.toLowerCase()) {
    case "warning": return "warning";
    case "critical":
    case "danger":
    case "error": return "danger";
    default: return "info";
  }
}

function eventTypeVariant(t: string): "info" | "warning" | "danger" | "success" {
  switch (t) {
    case "dwell": return "warning";
    case "presence": return "info";
    case "confidence_drop": return "danger";
    case "distance": return "success";
    default: return "info";
  }
}

function eventTypeIcon(t: string): string {
  switch (t) {
    case "dwell": return "\u23F3";
    case "presence": return "\u{1F464}";
    case "confidence_drop": return "\u26A0\uFE0F";
    case "distance": return "\u{1F4CF}";
    default: return "\u{1F514}";
  }
}

function EventRow({ event }: { event: PerceptionEvent }) {
  return (
    <div className="settings-toggle-row" style={{ justifyContent: "space-between" }}>
      <div className="settings-toggle-copy" style={{ flex: 1, minWidth: 0 }}>
        <span className="settings-toggle-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <span style={{ fontSize: "1.1em" }}>{eventTypeIcon(event.event_type)}</span>
          <span>{event.rule_name}</span>
          <Badge variant={eventTypeVariant(event.event_type)}>
            {event.event_type}
          </Badge>
        </span>
        <span className="settings-toggle-desc" style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          {event.class_name && <span>class: {event.class_name}</span>}
          {event.track_id != null && <span>track #{event.track_id}</span>}
          {event.confidence > 0 && <span>conf: {(event.confidence * 100).toFixed(0)}%</span>}
          {event.duration_seconds != null && <span>{event.duration_seconds.toFixed(1)}s</span>}
          {event.clip_frames > 0 && <span>{event.clip_frames} frames saved</span>}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexShrink: 0 }}>
        {event.auto_save && <Badge variant="success">saved</Badge>}
        <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>
          {humanizeTime(event.triggered_at)}
        </span>
      </div>
    </div>
  );
}

function payoutStatusVariant(s: string): "success" | "warning" | "danger" | "info" {
  switch (s?.toLowerCase()) {
    case "paid": return "success";
    case "pending":
    case "processing": return "warning";
    case "failed": return "danger";
    default: return "info";
  }
}

export default function OperatorDashboardPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const { events, total: eventsTotal, loading: eventsLoading, newCount, markSeen } = useOperatorEvents({
    pollIntervalMs: 5000,
    limit: 25,
  });

  useEffect(() => {
    let cancelled = false;
    api
      .get<DashboardData>("/operator/dashboard")
      .then((res) => {
        if (!cancelled) {
          setData(res.data);
          setError(null);
        }
      })
      .catch((err: { response?: { data?: { detail?: string } } }) => {
        if (!cancelled) setError(err.response?.data?.detail || "Failed to load dashboard");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const acknowledgeAlert = async (alertId: string) => {
    try {
      await api.post(`/operator/alerts/${alertId}/ack`);
      setData((prev) =>
        prev
          ? {
              ...prev,
              recent_alerts: prev.recent_alerts.map((a) =>
                a.id === alertId ? { ...a, acknowledged: true } : a,
              ),
              pending_alerts: Math.max(0, prev.pending_alerts - 1),
            }
          : prev,
      );
    } catch {
      /* ignore */
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <ErrorState
          title={t("operator.loadError", "Failed to load dashboard")}
          body={error || t("operator.noData", "No data available")}
          onRetry={() => { setLoading(true); setError(null); setRefreshKey((k) => k + 1); }}
        />
      </div>
    );
  }

  return (
    <PageShell
      accent="fleet"
      title={t("operator.title", "Operator Console")}
      subtitle={t("operator.subtitle", "Live monitoring and alert management")}
    >
      <div className="settings-grid">
        {/* Stats Row */}
        <section className="settings-panel">
          <h2>{t("operator.overview", "Overview")}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "var(--space-3)" }}>
            <StatCard
              label={t("operator.totalEarnings", "Total Earnings")}
              value={`MWK ${data.total_earnings_mwk.toLocaleString()}`}
            />
            <StatCard
              label={t("operator.totalAnnotations", "Total Annotations")}
              value={data.total_annotations.toLocaleString()}
            />
            <StatCard
              label={t("operator.pendingAlerts", "Pending Alerts")}
              value={data.pending_alerts.toLocaleString()}
            />
            <StatCard
              label={t("operator.totalEvents", "Perception Events")}
              value={eventsTotal.toLocaleString()}
            />
          </div>
        </section>

        {/* Live Perception Events */}
        <section className="settings-panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
            <h2 style={{ margin: 0 }}>
              {t("operator.liveEvents", "Live Perception Events")}
              {newCount > 0 && (
                <span style={{ marginLeft: "var(--space-2)", display: "inline-flex" }}>
                  <Badge variant="warning">
                    {t("operator.newCount", "{{count}} new", { count: newCount })}
                  </Badge>
                </span>
              )}
            </h2>
            <Button variant="ghost" size="sm" onClick={markSeen}>
              {t("operator.markSeen", "Mark read")}
            </Button>
          </div>
          {eventsLoading && events.length === 0 ? (
            <EmptyState
              title={t("operator.loadingEvents", "Loading events...")}
              body={t("operator.loadingEventsBody", "Connecting to perception engine")}
            />
          ) : events.length === 0 ? (
            <EmptyState
              title={t("operator.noEvents", "No perception events yet")}
              body={t("operator.noEventsBody", "Events will appear here when the live annotation engine detects dwell, presence, confidence drops, or close approach.")}
            />
          ) : (
            <div className="settings-toggle-list">
              {events.map((event) => (
                <EventRow key={event.id} event={event} />
              ))}
            </div>
          )}
          {eventsTotal > 0 && (
            <p style={{ marginTop: "var(--space-3)", fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>
              {t("operator.eventsTotal", "{{total}} total events recorded", { total: eventsTotal })}
            </p>
          )}
        </section>

        {/* System Alerts */}
        <section className="settings-panel">
          <h2>{t("operator.alerts", "System Alerts")}</h2>
          {data.recent_alerts.length === 0 ? (
            <EmptyState
              title={t("operator.noAlerts", "No alerts")}
              body={t("operator.noAlertsBody", "All systems operational.")}
            />
          ) : (
            <div className="settings-toggle-list">
              {data.recent_alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="settings-toggle-row"
                  style={{ justifyContent: "space-between" }}
                >
                  <div className="settings-toggle-copy">
                    <span className="settings-toggle-label">{alert.message}</span>
                    <span className="settings-toggle-desc">
                      {humanizeTime(alert.created_at)}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Badge variant={severityVariant(alert.severity)}>
                      {alert.severity}
                    </Badge>
                    {!alert.acknowledged && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => acknowledgeAlert(alert.id)}
                      >
                        {t("operator.acknowledge", "Acknowledge")}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Payout History */}
        <section className="settings-panel">
          <h2>{t("operator.payoutHistory", "Payout History")}</h2>
          {data.payout_history.length === 0 ? (
            <EmptyState
              title={t("operator.noPayouts", "No payouts")}
              body={t("operator.noPayoutsBody", "Payouts will appear here.")}
            />
          ) : (
            <div className="settings-toggle-list">
              {data.payout_history.map((payout) => (
                <div
                  key={payout.id}
                  className="settings-toggle-row"
                  style={{ justifyContent: "space-between" }}
                >
                  <div className="settings-toggle-copy">
                    <span className="settings-toggle-label">
                      MWK {payout.amount_mwk.toLocaleString()}
                    </span>
                    <span className="settings-toggle-desc">
                      {humanizeTime(payout.created_at)}
                    </span>
                  </div>
                  <Badge variant={payoutStatusVariant(payout.status)}>
                    {payout.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Node Status */}
        <section className="settings-panel">
          <h2>{t("operator.nodeStatus", "Node Status")}</h2>
          {data.associated_node_id ? (
            <div className="settings-toggle-list">
              <div className="settings-toggle-row">
                <div className="settings-toggle-copy">
                  <span className="settings-toggle-label">{t("operator.nodeId", "Node ID")}</span>
                  <span className="settings-toggle-desc">{data.associated_node_id}</span>
                </div>
                <Badge variant="success">linked</Badge>
              </div>
            </div>
          ) : (
            <EmptyState
              title={t("operator.noNode", "No node linked")}
              body={t("operator.noNodeBody", "Contact admin to link a node.")}
            />
          )}
        </section>
      </div>
    </PageShell>
  );
}
