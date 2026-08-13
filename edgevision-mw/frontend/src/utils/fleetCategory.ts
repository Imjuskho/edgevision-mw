import type { LucideIcon } from "lucide-react";
import { Camera, Fingerprint, Leaf, Map, Video } from "lucide-react";

export type FleetCategory = "ROAD" | "AGRI" | "WILDLIFE" | "DOC" | "BIOMETRIC";

export interface FleetCategoryMeta {
  icon: LucideIcon;
  color: string;
  labelKey: string;
}

export const FLEET_CATEGORY_META: Record<FleetCategory, FleetCategoryMeta> = {
  ROAD: { icon: Map, color: "var(--accent-blue)", labelKey: "fleet.categoryRoad" },
  AGRI: { icon: Leaf, color: "var(--accent-green)", labelKey: "fleet.categoryAgri" },
  WILDLIFE: { icon: Camera, color: "var(--accent-yellow)", labelKey: "fleet.categoryWildlife" },
  DOC: { icon: Video, color: "var(--accent-purple, #a855f7)", labelKey: "fleet.categoryDoc" },
  BIOMETRIC: { icon: Fingerprint, color: "var(--accent-teal, #14b8a6)", labelKey: "fleet.categoryBiometric" },
};

export function getFleetCategoryMeta(category: string | undefined): FleetCategoryMeta {
  const key = (category ?? "ROAD").toUpperCase() as FleetCategory;
  return FLEET_CATEGORY_META[key] ?? FLEET_CATEGORY_META.ROAD;
}

export function summarizeFleetStatus(nodes: { status?: string }[]) {
  return nodes.reduce(
    (acc, node) => {
      const status = (node.status ?? "OFFLINE").toUpperCase();
      if (status === "ONLINE") acc.online += 1;
      else if (status === "DEGRADED") acc.degraded += 1;
      else acc.offline += 1;
      return acc;
    },
    { online: 0, offline: 0, degraded: 0 },
  );
}
