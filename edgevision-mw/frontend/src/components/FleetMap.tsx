import { useTranslation } from "react-i18next";
import type { NodeInfo } from "../types";

interface FleetMapProps {
  nodes: NodeInfo[];
  onSelectNode: (nodeId: string) => void;
  selectedNodeId?: string;
}

const STATUS_COLORS: Record<string, string> = {
  ONLINE: "var(--accent-green)",
  OFFLINE: "var(--accent-red)",
  DEGRADED: "var(--accent-yellow)",
  MAINTENANCE: "var(--accent-purple)",
};

function projectNode(
  lat: number,
  lng: number,
  bounds: { minLat: number; maxLat: number; minLng: number; maxLng: number },
  width: number,
  height: number,
): { x: number; y: number } {
  const padding = 40;
  const usableW = width - padding * 2;
  const usableH = height - padding * 2;
  const x = padding + ((lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * usableW;
  const y = padding + ((bounds.maxLat - lat) / (bounds.maxLat - bounds.minLat)) * usableH;
  return { x, y };
}

function getBounds(nodes: NodeInfo[]) {
  const lats = nodes.map((n) => n.latitude).filter((v) => typeof v === "number" && v !== 0);
  const lngs = nodes.map((n) => n.longitude).filter((v) => typeof v === "number" && v !== 0);
  if (lats.length === 0) return { minLat: -17, maxLat: -9, minLng: 32, maxLng: 36 };
  const pad = 0.5;
  return {
    minLat: Math.min(...lats) - pad,
    maxLat: Math.max(...lats) + pad,
    minLng: Math.min(...lngs) - pad,
    maxLng: Math.max(...lngs) + pad,
  };
}

export function FleetMap({ nodes, onSelectNode, selectedNodeId }: FleetMapProps) {
  const { t } = useTranslation();
  const width = 600;
  const height = 400;
  const bounds = getBounds(nodes);

  const validNodes = nodes.filter(
    (n) => typeof n.latitude === "number" && n.latitude !== 0 && typeof n.longitude === "number" && n.longitude !== 0,
  );

  return (
    <div className="fleet-map-container" role="img" aria-label={t("fleet.mapLabel", "Fleet map showing node locations")}>
      <svg viewBox={`0 0 ${width} ${height}`} className="fleet-map-svg">
        {/* Grid lines */}
        {[0, 1, 2, 3, 4].map((i) => {
          const y = 40 + (i * (height - 80)) / 4;
          return <line key={`h${i}`} x1={40} y1={y} x2={width - 40} y2={y} stroke="var(--border-default)" strokeWidth={0.5} strokeDasharray="4 4" />;
        })}
        {[0, 1, 2, 3, 4].map((i) => {
          const x = 40 + (i * (width - 80)) / 4;
          return <line key={`v${i}`} x1={x} y1={40} x2={x} y2={height - 40} stroke="var(--border-default)" strokeWidth={0.5} strokeDasharray="4 4" />;
        })}

        {/* Axis labels */}
        {[0, 1, 2, 3, 4].map((i) => {
          const lat = bounds.maxLat - (i * (bounds.maxLat - bounds.minLat)) / 4;
          return (
            <text key={`lat${i}`} x={35} y={42 + (i * (height - 80)) / 4} textAnchor="end" fontSize={9} fill="var(--text-muted)">
              {lat.toFixed(1)}°
            </text>
          );
        })}
        {[0, 1, 2, 3, 4].map((i) => {
          const lng = bounds.minLng + (i * (bounds.maxLng - bounds.minLng)) / 4;
          return (
            <text key={`lng${i}`} x={40 + (i * (width - 80)) / 4} y={height - 28} textAnchor="middle" fontSize={9} fill="var(--text-muted)">
              {lng.toFixed(1)}°
            </text>
          );
        })}

        {/* Node markers */}
        {validNodes.map((node) => {
          const { x, y } = projectNode(node.latitude, node.longitude, bounds, width, height);
          const color = STATUS_COLORS[node.status] ?? "var(--text-muted)";
          const isSelected = node.node_id === selectedNodeId;
          const r = isSelected ? 10 : 7;

          return (
            <g
              key={node.node_id}
              className="fleet-map-node"
              onClick={() => onSelectNode(node.node_id)}
              style={{ cursor: "pointer" }}
              role="button"
              aria-label={`${node.node_id} — ${node.status}`}
            >
              {isSelected && (
                <circle cx={x} cy={y} r={r + 6} fill="none" stroke={color} strokeWidth={2} opacity={0.4} />
              )}
              <circle cx={x} cy={y} r={r} fill={color} stroke="var(--bg-surface)" strokeWidth={2} />
              <text x={x} y={y - r - 6} textAnchor="middle" fontSize={10} fontWeight={600} fill="var(--text-primary)">
                {node.node_id}
              </text>
              <text x={x} y={y + r + 14} textAnchor="middle" fontSize={8} fill="var(--text-muted)">
                {node.district || node.category}
              </text>
            </g>
          );
        })}

        {validNodes.length === 0 && (
          <text x={width / 2} y={height / 2} textAnchor="middle" fontSize={13} fill="var(--text-muted)">
            {t("fleet.noLocations", "No nodes with GPS coordinates")}
          </text>
        )}
      </svg>
    </div>
  );
}
