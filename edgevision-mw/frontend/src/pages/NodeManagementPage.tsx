import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Video } from "lucide-react";
import { usePageVisible } from "../hooks/usePageVisible";
import { useToast } from "../components/Toast";
import { useStudioSettings } from "../context/StudioSettingsContext";
import { studioApi } from "../services/api";
import { normalizeAlerts, normalizeNode } from "../utils/fleetNormalize";
import { getFleetCategoryMeta, summarizeFleetStatus } from "../utils/fleetCategory";
import { toStyle } from "../utils/toStyle";
import type { NodeAlert, NodeInfo } from "../types";
import { Button, EmptyState, ErrorState, Modal, StatCard } from "../components/ui";

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

  const loadAlerts = useCallback(async () => {
    try {
      const resp = await studioApi.getNodeAlerts();
      setAlerts(normalizeAlerts(resp.data));
    } catch {
      setAlerts([]);
    }
  }, []);

  useEffect(() => {
    loadNodes();
    loadAlerts();
    const interval = setInterval(() => {
      if (document.visibilityState !== "hidden") {
        loadNodes();
        loadAlerts();
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [loadNodes, loadAlerts, pageVisible]);

  const handleSelectNode = useCallback(
    (node: NodeInfo) => {
      navigate(`/nodes/${encodeURIComponent(node.node_id)}`);
    },
    [navigate],
  );

  const loadNodeDetail = useCallback(async (node: NodeInfo) => {
    setSelectedNode(node);
    setCmdResult(null);
    try {
      const resp = await studioApi.getNodeDetail(node.node_id);
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
  }, []);

  useEffect(() => {
    if (!urlNodeId || nodes.length === 0) return;
    const match = nodes.find((n) => n.node_id === decodeURIComponent(urlNodeId));
    if (match) void loadNodeDetail(match);
  }, [urlNodeId, nodes, loadNodeDetail]);

  useEffect(() => {
    if (!urlNodeId) {
      setSelectedNode(null);
      setTelemetry([]);
    }
  }, [urlNodeId]);

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
      </header>

      <div className="fleet-layout">
        <div className="fleet-list">
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
                {telemetry.length > 0 && (
                  <div className="telemetry-grid">
                    {Object.entries(telemetry[0] ?? {})
                      .slice(0, 8)
                      .map(([k, v]) => (
                        <div key={k} className="detail-field">
                          <label>{k}</label>
                          <span>{String(v ?? "—")}</span>
                        </div>
                      ))}
                  </div>
                )}
                <div className="fleet-live-feed-placeholder">
                  <Video size={24} aria-hidden />
                  <p>{t("fleet.liveFeedPlaceholder")}</p>
                </div>
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
