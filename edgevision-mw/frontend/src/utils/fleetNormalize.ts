import type { NodeAlert, NodeInfo } from "../types";

function inferSeverity(message: string): NodeAlert["severity"] {
  const lower = message.toLowerCase();
  if (lower.includes("critical") || lower.includes("offline") || lower.includes("fail")) {
    return "critical";
  }
  if (lower.includes("warn") || lower.includes("low") || lower.includes("degraded")) {
    return "warning";
  }
  return "info";
}

/** Normalize fleet list API rows (backend uses node_id, last_sync, etc.). */
export function normalizeNode(raw: Record<string, unknown>): NodeInfo {
  const nodeId = String(raw.node_id ?? raw.node_uuid ?? raw.id ?? "");
  const lat = raw.latitude ?? raw.lat;
  const lng = raw.longitude ?? raw.lng ?? raw.lon;

  return {
    id: nodeId,
    node_id: nodeId,
    district: String(raw.district ?? "—"),
    latitude: typeof lat === "number" ? lat : Number(lat) || 0,
    longitude: typeof lng === "number" ? lng : Number(lng) || 0,
    category: String(raw.category ?? "ROAD"),
    hardware_profile: (raw.hardware_profile as Record<string, unknown>) ?? {},
    status: String(raw.status ?? "OFFLINE"),
    last_heartbeat_at: raw.last_heartbeat_at
      ? String(raw.last_heartbeat_at)
      : raw.last_sync
        ? String(raw.last_sync)
        : null,
    is_enabled: raw.is_enabled !== false,
    created_at: String(raw.created_at ?? ""),
  };
}

/** Normalize alerts API — backend returns { items: [{ node_id, alerts: string[] }] }. */
export function normalizeAlerts(data: unknown): NodeAlert[] {
  if (!data) return [];

  const rows = Array.isArray(data)
    ? data
    : typeof data === "object" && data !== null && Array.isArray((data as { items?: unknown[] }).items)
      ? (data as { items: unknown[] }).items
      : [];

  const alerts: NodeAlert[] = [];

  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    const nodeId = String(r.node_id ?? r.node_uuid ?? "");
    const nodeName = String(r.node_name ?? nodeId);

    if (Array.isArray(r.alerts)) {
      for (const msg of r.alerts) {
        const text = String(msg);
        alerts.push({
          node_id: nodeId,
          node_name: nodeName,
          alert: text,
          severity: inferSeverity(text),
          timestamp: String(r.timestamp ?? ""),
        });
      }
      continue;
    }

    if (r.alert) {
      alerts.push({
        node_id: nodeId,
        node_name: nodeName,
        alert: String(r.alert),
        severity: (r.severity as NodeAlert["severity"]) ?? inferSeverity(String(r.alert)),
        timestamp: String(r.timestamp ?? ""),
      });
    }
  }

  return alerts;
}
