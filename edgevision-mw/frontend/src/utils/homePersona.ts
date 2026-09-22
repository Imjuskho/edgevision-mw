import type { UserRole } from "./roles";
import { normalizeRole } from "./roles";

export type HomePersona = "ANNOTATOR" | "QA" | "OPERATOR" | "FIELD_TECH" | "BUYER" | "ADMIN";

export interface HomePersonaConfig {
  persona: HomePersona;
  showQueue: boolean;
  showFleet: boolean;
  showHealthRings: boolean;
  showReviewOps: boolean;
  showIngestion: boolean;
  showMarketplacePlaceholder: boolean;
  primaryAction: "label" | "review" | "fleet" | "browse";
}

export function resolveHomePersona(role: string | undefined): HomePersona {
  const r = normalizeRole(role);
  if (r === "ADMIN") return "ADMIN";
  if (r === "QA") return "QA";
  if (r === "OPERATOR") return "OPERATOR";
  if (r === "FIELD_TECH") return "FIELD_TECH";
  if (r === "BUYER") return "BUYER";
  return "ANNOTATOR";
}

export function getHomePersonaConfig(role: string | undefined): HomePersonaConfig {
  const persona = resolveHomePersona(role);
  switch (persona) {
    case "ADMIN":
    case "QA":
      return {
        persona,
        showQueue: true,
        showFleet: true,
        showHealthRings: true,
        showReviewOps: true,
        showIngestion: false,
        showMarketplacePlaceholder: false,
        primaryAction: "review",
      };
    case "OPERATOR":
      return {
        persona,
        showQueue: false,
        showFleet: true,
        showHealthRings: false,
        showReviewOps: false,
        showIngestion: true,
        showMarketplacePlaceholder: false,
        primaryAction: "fleet",
      };
    case "FIELD_TECH":
      return {
        persona,
        showQueue: false,
        showFleet: true,
        showHealthRings: false,
        showReviewOps: false,
        showIngestion: false,
        showMarketplacePlaceholder: false,
        primaryAction: "fleet",
      };
    case "BUYER":
      return {
        persona,
        showQueue: false,
        showFleet: false,
        showHealthRings: false,
        showReviewOps: false,
        showIngestion: false,
        showMarketplacePlaceholder: false,
        primaryAction: "browse",
      };
    default:
      return {
        persona: "ANNOTATOR",
        showQueue: true,
        showFleet: false,
        showHealthRings: true,
        showReviewOps: false,
        showIngestion: false,
        showMarketplacePlaceholder: false,
        primaryAction: "label",
      };
  }
}

export function roleSupportsTourTrack(role: UserRole | string | undefined): HomePersona {
  return resolveHomePersona(role);
}
