import type { View } from "../routes/paths";

export type UserRole =
  | "ADMIN"
  | "QA"
  | "ANNOTATOR"
  | "OPERATOR"
  | "BUYER"
  | "FIELD_TECH";

/** Annotator — labeling views only. */
export const ANNOTATOR_VIEWS: View[] = [
  "home",
  "annotate",
  "agriAnnotate",
  "segment",
  "datasets",
  "upload",
  "queue",
  "settings",
];

/** Buyer — marketplace + subject views. */
export const BUYER_VIEWS: View[] = [
  "home",
  "datasets",
  "buyer",
  "subject",
  "settings",
];

/** QA / admin — full navigation. */
export const ADMIN_QA_VIEWS: View[] = [
  "home",
  "annotate",
  "agriAnnotate",
  "segment",
  "datasets",
  "upload",
  "queue",
  "admin",
  "review",
  "dedup",
  "roadAnalysis",
  "agriAnalysis",
  "health",
  "fleet",
  "liveAnnotate",
  "roadTaxonomy",
  "agriTaxonomy",
  "training",
  "export",
  "settings",
  "operator",
  "buyer",
  "subject",
];

/** Operator — data pipeline + quality tools. */
export const OPERATOR_VIEWS: View[] = [
  "home",
  "annotate",
  "agriAnnotate",
  "segment",
  "datasets",
  "upload",
  "queue",
  "dedup",
  "export",
  "training",
  "fleet",
  "settings",
  "operator",
];

/** Route-level role requirements (backend-aligned). */
export const VIEW_ROLE_REQUIREMENTS: Partial<Record<View, UserRole[]>> = {
  admin: ["ADMIN", "QA"],
  review: ["ADMIN", "QA"],
  roadAnalysis: ["ADMIN", "QA"],
  agriAnalysis: ["ADMIN", "QA"],
  dedup: ["ADMIN", "OPERATOR"],
  training: ["ADMIN", "OPERATOR"],
  export: ["ADMIN", "OPERATOR"],
  fleet: ["ADMIN", "OPERATOR", "FIELD_TECH"],
  settings: ["ADMIN", "QA", "ANNOTATOR", "OPERATOR", "BUYER", "FIELD_TECH"],
};

export function normalizeRole(role: string | undefined): UserRole {
  const upper = (role ?? "ANNOTATOR").toUpperCase() as UserRole;
  return upper;
}

export function isAdminRole(role: string | undefined): boolean {
  const r = normalizeRole(role);
  return r === "ADMIN" || r === "QA";
}

export function isOperatorRole(role: string | undefined): boolean {
  return normalizeRole(role) === "OPERATOR";
}

export function isAnnotatorRole(role: string | undefined): boolean {
  return normalizeRole(role) === "ANNOTATOR";
}

export function viewsForRole(role: string | undefined): View[] {
  const r = normalizeRole(role);
  if (r === "ADMIN" || r === "QA") return ADMIN_QA_VIEWS;
  if (r === "OPERATOR") return OPERATOR_VIEWS;
  if (r === "ANNOTATOR") return ANNOTATOR_VIEWS;
  if (r === "BUYER") return BUYER_VIEWS;
  if (r === "FIELD_TECH") return ["home", "fleet", "datasets", "settings"];
  return ANNOTATOR_VIEWS;
}

export function canAccessView(role: string | undefined, view: View): boolean {
  const allowed = viewsForRole(role);
  if (!allowed.includes(view)) return false;
  const required = VIEW_ROLE_REQUIREMENTS[view];
  if (!required) return true;
  return required.includes(normalizeRole(role));
}

export function canManageOperationalSettings(role: string | undefined): boolean {
  return normalizeRole(role) === "ADMIN";
}

export function canUseExpertFeatures(role: string | undefined): boolean {
  const r = normalizeRole(role);
  return r === "ADMIN" || r === "QA" || r === "OPERATOR";
}
