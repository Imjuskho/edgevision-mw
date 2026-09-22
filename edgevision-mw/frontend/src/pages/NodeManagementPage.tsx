import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { usePageVisible } from "../hooks/usePageVisible";
import { useToast } from "../components/Toast";
import { useStudioSettings } from "../context/StudioSettingsContext";
import { studioApi } from "../services/api";
import { normalizeAlerts, normalizeNode } from "../utils/fleetNormalize";
import { getFleetCategoryMeta, summarizeFleetStatus } from "../utils/fleetCategory";
import { toStyle } from "../utils/toStyle";
import type { NodeAlert, NodeInfo } from "../types";
import { Button, EmptyState, ErrorState, Modal, StatCard } from "../components/ui";
import { FleetMap } from "../components/FleetMap";

const STATUS_CLASS: Record<string, string> = {
  ONLINE: "fleet-stat--online",
  OFFLINE: "fleet-stat--offline",
  DEGRADED: "fleet-stat--offline",
};

export default function NodeManagementPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { nodeId: urlNodeId } = useParams<{ nodeId?: string }>();
  const navigate = useNavigate();
  const pageVisible = usePageVisible();
  const { expertMode } = useStudioSettings();
  const [nodes, setNodes] = useState<NodeInfo[]>([]);
  const [alerts, setAlerts] = useState<NodeAlert[]>([]);
  const [selectedNode, setSelectedNode] = useState<NodeInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [telemetry, setTelemetry] = useState<Record<string, unknown>[]>([]);
  const [cmdResult, setCmdResult] = useState<string | null>(null);
  const [cmdModalOpen, setCmdModalOpen] = useState(false);
  const [pendingCmd, setPendingCmd] = useState<string | null>(null);
  const [mapView, setMapView] = useState(false);

  const [prevUrlNodeId, setPrevUrlNodeId] = useState(urlNodeId);
  if (urlNodeId !== prevUrlNodeId) {
    setPrevUrlNodeId(urlNodeId);
    if (!urlNodeId) {
      setSelectedNode(null);
      setTelemetry([]);
    }
  }

  const loadNodes = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await studioApi.listNodes();
      const raw = resp.data;
      const list = Array.isArray(raw) ? raw : (raw as { items?: unknown[] })?.items ?? [];
      setNodes(list.map((row) => normalizeNode(row as Record<string, unknown>)));
      setLoadError(false);
    } catch {
      setNodes([]);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadAll = async () => {
      try {
        const resp = await studioApi.listNodes();
        const raw = resp.data;
        const list = Array.isArray(raw) ? raw : (raw as { items?: unknown[] })?.items ?? [];
        setNodes(list.map((row) => normalizeNode(row as Record<string, unknown>)));
        setLoadError(false);
      } catch {
        setNodes([]);
        setLoadError(true);
      } finally {
        setLoading(false);
      }
      try {
        const alertsResp = await studioApi.getNodeAlerts();
        setAlerts(normalizeAlerts(alertsResp.data));
      } catch {
        setAlerts([]);
      }
    };
    void loadAll();
    const interval = setInterval(() => {
      if (document.visibilityState !== "hidden") {
        void loadAll();
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [pageVisible]);

  const handleSelectNode = useCallback(
    (node: NodeInfo) => {
      navigate(`/nodes/${encodeURIComponent(node.node_id)}`);
    },
    [navigate],
  );

  useEffect(() => {
    if (!urlNodeId || nodes.length === 0) return;
    const match = nodes.find((n) => n.node_id === decodeURIComponent(urlNodeId));
    if (!match) return;
    const load = async () => {
      setSelectedNode(match);
      setCmdResult(null);
      try {
        const resp = await studioApi.getNodeDetail(match.node_id);
        const data = resp.data ?? {};
        const heartbeats =
          (data as { recent_heartbeats?: Record<string, unknown>[] }).recent_heartbeats ??
          (data as { recent_telemetry?: Record<string, unknown>[] }).recent_telemetry ??
          [];
        setTelemetry(Array.isArray(heartbeats) ? heartbeats : []);

        const detailNode = (data as { node?: Record<string, unknown> }).node;
        if (detailNode) {
          setSelectedNode((prev) => (prev ? { ...prev, ...normalizeNode(detailNode) } : normalizeNode(detailNode)));
        }
      } catch {
        setTelemetry([]);
      }
    };
    void load();
  }, [urlNodeId, nodes]);

  const commandLabel = (cmd: string) => {
    if (cmd === "UPDATE_FIRMWARE") return t("fleet.updateFirmware");
    if (cmd === "EMERGENCY_UPLOAD") return t("fleet.emergencyUpload");
    if (cmd === "REBOOT") return t("fleet.reboot");
    if (cmd === "THROTTLE") return t("fleet.throttle");
    return cmd.charAt(0) + cmd.slice(1).toLowerCase();
  };

  const handleSendCommand = useCallback(
    async (cmd: string) => {
      if (!selectedNode) return;
      setPendingCmd(cmd);
      setCmdModalOpen(true);
    },
    [selectedNode],
  );

  const confirmSendCommand = useCallback(async () => {
    if (!selectedNode || !pendingCmd) return;
    const cmd = pendingCmd;
    setCmdModalOpen(false);
    setCmdResult(t("fleet.cmdSending", { cmd }));
    try {
      await studioApi.sendNodeCommand(selectedNode.node_id, cmd);
      setCmdResult(t("fleet.cmdQueued", { cmd }));
      showToast(t("fleet.cmdQueued", { cmd }), "success");
    } catch {
      setCmdResult(t("fleet.cmdFailed"));
      showToast(t("fleet.cmdFailed"), "error");
    } finally {
      setPendingCmd(null);
    }
  }, [selectedNode, pendingCmd, t, showToast]);

  const statusSummary = summarizeFleetStatus(nodes);

  const formatPosition = (node: NodeInfo) => {
    if (!node.latitude && !node.longitude) return t("fleet.positionUnknown", "—");
    return `${node.latitude.toFixed(4)}, ${node.longitude.toFixed(4)}`;
  };

  return (
    <div className="fleet-page">
      <header className="fleet-page-header">
        <h1>{t("fleet.title")}</h1>
        <div className="fleet-stats-row fleet-stats-row--cards">
          <StatCard label={t("fleet.total")} value={nodes.length} />
          <StatCard label={t("fleet.online")} value={statusSummary.online} className={STATUS_CLASS.ONLINE} />
          <StatCard label={t("fleet.degraded")} value={statusSummary.degraded} />
          <StatCard label={t("fleet.offlineDegraded")} value={statusSummary.offline} className={STATUS_CLASS.OFFLINE} />
          <StatCard label={t("fleet.alerts")} value={alerts.length} />
        </div>
        <Button variant="secondary" size="sm" onClick={() => void loadNodes()}>
          {t("fleet.refresh")}
        </Button>
        <Button
          variant={mapView ? "primary" : "secondary"}
          size="sm"
          onClick={() => setMapView(!mapView)}
        >
          {mapView ? t("fleet.listView", "List") : t("fleet.mapView", "Map")}
        </Button>
      </header>

      <div className="fleet-layout">
        <div className="fleet-list">
          {mapView ? (
            <FleetMap
              nodes={nodes}
              onSelectNode={(id) => {
                const node = nodes.find((n) => n.node_id === id);
                if (node) handleSelectNode(node);
              }}
              selectedNodeId={selectedNode?.node_id}
            />
          ) : (
            <>
              <h3>{t("fleet.nodes")}</h3>
          {loading && <p className="empty-state">{t("fleet.loading")}</p>}
          {!loading && loadError && (
            <ErrorState
              title={t("fleet.loadFailed")}
              body={t("fleet.emptyBody")}
              onRetry={() => void loadNodes()}
              retryLabel={t("fleet.refresh")}
            />
          )}
          {!loading && !loadError && nodes.length === 0 && (
            <EmptyState title={t("fleet.emptyTitle")} body={t("fleet.emptyBody")} />
          )}
          {nodes.map((node) => {
            const category = getFleetCategoryMeta(node.category);
            const CategoryIcon = category.icon;
            return (
            <button
              key={node.node_id}
              type="button"
              className={`fleet-node-card ${selectedNode?.node_id === node.node_id ? "selected" : ""}`}
              onClick={() => handleSelectNode(node)}
            >
              <div className="fleet-node-header">
                <span className="fleet-node-icon" style={toStyle({ color: category.color })}>
                  <CategoryIcon size={16} aria-hidden />
                </span>
                <span className="fleet-node-id">{node.node_id}</span>
                <span className={`fleet-node-status fleet-node-status--${node.status.toLowerCase()}`}>
                  ● {node.status}
                </span>
              </div>
              <div className="fleet-node-meta">
                <span>{node.district}</span>
                <span>{node.is_enabled ? t("fleet.enabled") : t("fleet.disabled")}</span>
              </div>
            </button>
          );})}
            </>
          )}
        </div>

        <div className="fleet-detail">
          {!selectedNode && (
            <div className="empty-state">
              <p>{t("fleet.selectNode")}</p>
            </div>
          )}
          {selectedNode && (
            <>
              <div className="fleet-detail-header">
                <h3>{selectedNode.node_id}</h3>
                <span className={`fleet-node-status-badge fleet-node-status-badge--${selectedNode.status.toLowerCase()}`}>
                  {selectedNode.status}
                </span>
              </div>
              <div className="fleet-detail-grid">
                <div className="detail-field">
                  <label>{t("fleet.district")}</label>
                  <span>{selectedNode.district}</span>
                </div>
                <div className="detail-field">
                  <label>{t("fleet.category")}</label>
                  <span>{selectedNode.category}</span>
                </div>
                <div className="detail-field">
                  <label>{t("fleet.position")}</label>
                  <span>{formatPosition(selectedNode)}</span>
                </div>
                <div className="detail-field">
                  <label>{t("fleet.lastHeartbeat")}</label>
                  <span>{selectedNode.last_heartbeat_at ?? t("fleet.never")}</span>
                </div>
              </div>

              {alerts.filter((a) => a.node_id === selectedNode.node_id).length > 0 && (
                <div className="fleet-alerts-section">
                  <h4>{t("fleet.activeAlerts")}</h4>
                  {alerts
                    .filter((a) => a.node_id === selectedNode.node_id)
                    .map((a, i) => (
                      <div key={`${a.node_id}-alert-${i}`} className={`alert-card ${a.severity}`}>
                        <span className="alert-severity">●</span>
                        <span>{a.alert}</span>
                      </div>
                    ))}
                </div>
              )}

              <div className="fleet-telemetry-section">
                <h4>{t("fleet.telemetryTitle")}</h4>
                {telemetry.length === 0 && <p className="empty-state">{t("fleet.noTelemetry")}</p>}
                {telemetry.length > 0 && (() => {
                  const hb = telemetry[0] as Record<string, unknown>;
                  const solar = Number(hb.solar_input_watts ?? 0);
                  const cpuTemp = Number(hb.cpu_temp_celsius ?? 0);
                  const battery = Number(hb.battery_voltage ?? 0);
                  const lte = Number(hb.lte_rssi_dbm ?? 0);
                  const storageUsed = Number(hb.storage_used_gb ?? 0);
                  const storageTotal = Number(hb.storage_total_gb ?? 0);
                  const storagePct = storageTotal > 0 ? Math.round((storageUsed / storageTotal) * 100) : 0;

                  const weatherCondition = solar > 50 ? "clear" : solar > 20 ? "cloudy" : solar > 5 ? "overcast" : "night/rain";
                  const weatherIcon = solar > 50 ? "\u2600\uFE0F" : solar > 20 ? "\u2601\uFE0F" : solar > 5 ? "\u{1F325}\uFE0F" : "\u{1F319}";
                  const tempWarning = cpuTemp > 70 ? "overheating" : cpuTemp > 50 ? "warm" : "normal";
                  const batteryPct = battery > 12.6 ? 100 : battery > 12.0 ? 75 : battery > 11.5 ? 50 : battery > 11.0 ? 25 : 0;
                  const signalQuality = lte > -70 ? "excellent" : lte > -85 ? "good" : lte > -100 ? "fair" : "poor";

                  return (
                    <>
                      {/* Environmental Conditions */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
                        <div style={{ padding: "var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-sm)", textAlign: "center" }}>
                          <div style={{ fontSize: "1.5em", marginBottom: "var(--space-1)" }}>{weatherIcon}</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>{t("fleet.weather", "Weather")}</div>
                          <div style={{ fontWeight: 600, textTransform: "capitalize" }}>{weatherCondition}</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>{solar.toFixed(0)}W solar</div>
                        </div>
                        <div style={{ padding: "var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-sm)", textAlign: "center" }}>
                          <div style={{ fontSize: "1.5em", marginBottom: "var(--space-1)" }}>{tempWarning === "overheating" ? "\u{1F321}\uFE0F" : tempWarning === "warm" ? "\u{1F321}" : "\u2744\uFE0F"}</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>{t("fleet.temperature", "Temperature")}</div>
                          <div style={{ fontWeight: 600 }}>{cpuTemp.toFixed(0)}\u00B0C</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: tempWarning === "overheating" ? "var(--color-danger)" : "var(--text-muted)" }}>{tempWarning}</div>
                        </div>
                        <div style={{ padding: "var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-sm)", textAlign: "center" }}>
                          <div style={{ fontSize: "1.5em", marginBottom: "var(--space-1)" }}>{batteryPct > 50 ? "\u{1F50B}" : batteryPct > 25 ? "\u{1F50C}" : "\u{1F6A8}"}</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>{t("fleet.battery", "Battery")}</div>
                          <div style={{ fontWeight: 600 }}>{battery.toFixed(1)}V</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: batteryPct <= 25 ? "var(--color-danger)" : "var(--text-muted)" }}>{batteryPct}%</div>
                        </div>
                        <div style={{ padding: "var(--space-3)", background: "var(--bg-secondary)", borderRadius: "var(--radius-sm)", textAlign: "center" }}>
                          <div style={{ fontSize: "1.5em", marginBottom: "var(--space-1)" }}>{signalQuality === "excellent" || signalQuality === "good" ? "\u{1F4F6}" : "\u{1F4F5}"}</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>{t("fleet.signal", "Signal")}</div>
                          <div style={{ fontWeight: 600 }}>{lte.toFixed(0)} dBm</div>
                          <div style={{ fontSize: "var(--font-size-xs)", color: signalQuality === "poor" ? "var(--color-danger)" : "var(--text-muted)" }}>{signalQuality}</div>
                        </div>
                      </div>
                      {/* Storage */}
                      <div style={{ marginBottom: "var(--space-3)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--font-size-xs)", marginBottom: "var(--space-1)" }}>
                          <span>{t("fleet.storage", "Storage")}</span>
                          <span>{storageUsed.toFixed(1)} / {storageTotal.toFixed(1)} GB ({storagePct}%)</span>
                        </div>
                        <div style={{ height: 6, background: "var(--bg-secondary)", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ height: "100%", width: `${storagePct}%`, background: storagePct > 90 ? "var(--color-danger)" : storagePct > 70 ? "var(--color-warning)" : "var(--color-success)", borderRadius: 3, transition: "width 0.3s" }} />
                        </div>
                      </div>
                      {/* Raw telemetry */}
                      <details>
                        <summary style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)", cursor: "pointer", marginBottom: "var(--space-2)" }}>{t("fleet.rawTelemetry", "Raw telemetry")}</summary>
                        <div className="telemetry-grid">
                          {Object.entries(hb).slice(0, 8).map(([k, v]) => (
                            <div key={k} className="detail-field">
                              <label>{k}</label>
                              <span>{String(v ?? "\u2014")}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    </>
                  );
                })()}
                {(() => {
                  const latestHb = telemetry.length > 0 ? (telemetry[0] as Record<string, unknown>) : null;
                  const eventsCaptured = latestHb ? Number(latestHb.events_captured ?? 0) : 0;
                  const eventsUploaded = latestHb ? Number(latestHb.events_uploaded ?? 0) : 0;
                  const lastCaptureTime = latestHb?.timestamp ?? latestHb?.captured_at ?? null;

                  if (eventsCaptured === 0 && telemetry.length === 0) {
                    return (
                      <div className="fleet-last-snapshot fleet-last-snapshot--empty">
                        <p className="text-secondary text-sm">
                          {t("fleet.noCapturesYet", "No captures yet")}
                        </p>
                      </div>
                    );
                  }
                  return (
                    <div className="fleet-last-snapshot">
                      <h4>{t("fleet.lastSnapshot", "Last Snapshot")}</h4>
                      <div className="fleet-snapshot-stats">
                        <span>{t("fleet.eventsCaptured", "{{count}} captured", { count: eventsCaptured })}</span>
                        <span>{t("fleet.eventsUploaded", "{{count}} uploaded", { count: eventsUploaded })}</span>
                        {lastCaptureTime && (
                          <span className="text-secondary text-xs">
                            {t("fleet.lastCaptureTime", "Last: {{time}}", {
                              time: new Date(String(lastCaptureTime)).toLocaleString(),
                            })}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}
              </div>

              {expertMode && (
              <div className="fleet-commands-section">
                <h4>{t("fleet.management")}</h4>
                <div className="fleet-command-buttons">
                  {["REBOOT", "UPDATE_FIRMWARE", "EMERGENCY_UPLOAD", "THROTTLE"].map((cmd) => (
                    <button key={cmd} type="button" className="btn btn-sm" onClick={() => void handleSendCommand(cmd)}>
                      {commandLabel(cmd)}
                    </button>
                  ))}
                </div>
                {cmdResult && <p className="cmd-result">{cmdResult}</p>}
              </div>
              )}
              {!expertMode && (
                <p className="fleet-expert-hint text-secondary text-sm">
                  {t("fleet.expertHint", "Enable Expert mode in Settings to send fleet commands.")}
                </p>
              )}
            </>
          )}
        </div>

        <div className="fleet-alerts-panel">
          <h3>{t("fleet.alertsPanel")}</h3>
          {alerts.length === 0 && <p className="empty-state">{t("fleet.noAlerts")}</p>}
          {alerts.map((a, i) => (
            <div key={`alert-${a.node_id}-${i}`} className={`alert-card ${a.severity}`}>
              <div className="alert-header">
                <span className={`alert-severity-dot alert-severity-dot--${a.severity}`} />
                <span className="alert-node">{a.node_name ?? a.node_id}</span>
              </div>
              <p className="alert-message">{a.alert}</p>
            </div>
          ))}
        </div>
      </div>

      <Modal
        open={cmdModalOpen}
        onClose={() => {
          setCmdModalOpen(false);
          setPendingCmd(null);
        }}
        title={t("fleet.management")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCmdModalOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" onClick={() => void confirmSendCommand()}>
              {pendingCmd ? commandLabel(pendingCmd) : t("common.ok")}
            </Button>
          </>
        }
      >
        <p>
          {pendingCmd && selectedNode
            ? t("fleet.cmdConfirm", { label: commandLabel(pendingCmd), nodeId: selectedNode.node_id })
            : t("fleet.selectNode")}
        </p>
        {cmdResult && <p className="cmd-result">{cmdResult}</p>}
      </Modal>
    </div>
  );
}
