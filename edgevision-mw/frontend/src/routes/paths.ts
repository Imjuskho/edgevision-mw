/** View keys aligned with legacy App.tsx navigation. */
export type View =
  | "home"
  | "annotate"
  | "agriAnnotate"
  | "segment"
  | "health"
  | "dedup"
  | "export"
  | "upload"
  | "queue"
  | "admin"
  | "review"
  | "reviewFast"
  | "roadAnalysis"
  | "roadTaxonomy"
  | "agriAnalysis"
  | "agriTaxonomy"
  | "training"
  | "datasets"
  | "fleet"
  | "liveAnnotate"
  | "settings";

export interface ParsedRoute {
  view: View;
  datasetId?: string;
  nodeId?: string;
}

/** Views that require a dataset ID in the URL. */
export const DATASET_SCOPED_VIEWS: View[] = [
  "home",
  "annotate",
  "agriAnnotate",
  "segment",
  "upload",
  "health",
  "dedup",
  "export",
  "roadAnalysis",
  "agriAnalysis",
  "training",
  "liveAnnotate",
  "reviewFast",
];

/** Suffix appended to `/datasets/:datasetId` for each dataset-scoped view. */
const DATASET_VIEW_SUFFIX: Partial<Record<View, string>> = {
  home: "",
  annotate: "/annotate",
  agriAnnotate: "/agri-annotate",
  segment: "/segment",
  upload: "/upload",
  health: "/health",
  dedup: "/dedup",
  export: "/export",
  roadAnalysis: "/road-analysis",
  agriAnalysis: "/agri-analysis",
  training: "/training",
  liveAnnotate: "/live-annotate",
  reviewFast: "/review/fast",
};

/** Global (non-dataset) URL paths. */
export const GLOBAL_PATHS: Record<View, string> = {
  home: "/",
  annotate: "/annotate",
  agriAnnotate: "/agri-annotate",
  segment: "/segment",
  datasets: "/datasets",
  upload: "/upload",
  queue: "/queue",
  admin: "/assign",
  review: "/review",
  reviewFast: "/review/fast",
  dedup: "/dedup",
  roadAnalysis: "/road-analysis",
  agriAnalysis: "/agri-analysis",
  health: "/health",
  fleet: "/nodes",
  liveAnnotate: "/live-annotate",
  roadTaxonomy: "/road-taxonomy",
  agriTaxonomy: "/agri-taxonomy",
  training: "/training",
  export: "/export",
  settings: "/settings",
};

/** Legacy flat paths kept for redirects. */
const LEGACY_FLAT_PATHS = new Set(
  DATASET_SCOPED_VIEWS.filter((v) => v !== "home").map((v) => GLOBAL_PATHS[v]),
);

const SUFFIX_TO_VIEW = Object.entries(DATASET_VIEW_SUFFIX).reduce<Record<string, View>>(
  (acc, [view, suffix]) => {
    acc[suffix ?? ""] = view as View;
    return acc;
  },
  {},
);

function normalizePath(path: string): string {
  if (path === "/") return "/";
  return path.replace(/\/+$/, "") || "/";
}

function encodeId(id: string): string {
  return encodeURIComponent(id);
}

function decodeId(id: string): string {
  return decodeURIComponent(id);
}

/** Parse a URL pathname into view + entity IDs. */
export function parsePath(pathname: string): ParsedRoute {
  const path = normalizePath(pathname);

  const datasetMatch = path.match(/^\/datasets\/([^/]+)(\/.*)?$/);
  if (datasetMatch) {
    const datasetId = decodeId(datasetMatch[1]);
    const suffix = datasetMatch[2] ?? "";
    const view = SUFFIX_TO_VIEW[suffix] ?? "home";
    return { view, datasetId };
  }

  if (path === "/datasets") {
    return { view: "datasets" };
  }

  const nodeMatch = path.match(/^\/nodes\/([^/]+)$/);
  if (nodeMatch) {
    return { view: "fleet", nodeId: decodeId(nodeMatch[1]) };
  }

  if (path === "/nodes") {
    return { view: "fleet" };
  }

  const globalEntry = Object.entries(GLOBAL_PATHS).find(([, p]) => p === path);
  if (globalEntry) {
    return { view: globalEntry[0] as View };
  }

  return { view: "home" };
}

/** Build a URL for a view, embedding entity IDs when provided. */
export function buildPath(view: View, opts?: { datasetId?: string; nodeId?: string }): string {
  const { datasetId, nodeId } = opts ?? {};

  if (view === "fleet") {
    return nodeId ? `/nodes/${encodeId(nodeId)}` : "/nodes";
  }

  if (view === "datasets") {
    return "/datasets";
  }

  const suffix = DATASET_VIEW_SUFFIX[view];
  if (suffix !== undefined && datasetId) {
    return `/datasets/${encodeId(datasetId)}${suffix}`;
  }

  if (DATASET_SCOPED_VIEWS.includes(view) && view !== "home" && !datasetId) {
    return "/datasets";
  }

  return GLOBAL_PATHS[view];
}

/** Build URL when switching datasets via the sidebar select. Preserves nested view. */
export function buildPathForDatasetSwitch(
  currentView: View,
  currentParsed: ParsedRoute,
  newDatasetId: string,
): string {
  if (!newDatasetId) return "/";

  if (
    currentParsed.datasetId &&
    DATASET_SCOPED_VIEWS.includes(currentView) &&
    currentView !== "home"
  ) {
    return buildPath(currentView, { datasetId: newDatasetId });
  }

  return buildPath("home", { datasetId: newDatasetId });
}

/** @deprecated Use parsePath().view */
export function pathToView(pathname: string): View {
  return parsePath(pathname).view;
}

/** @deprecated Use buildPath() */
export function viewToPath(view: View): string {
  return buildPath(view);
}

export function isLegacyFlatPath(pathname: string): boolean {
  return LEGACY_FLAT_PATHS.has(normalizePath(pathname));
}

export const VIEW_TITLES: Record<View, string> = {
  home: "Dashboard",
  annotate: "Annotate Images",
  agriAnnotate: "Agri Annotate",
  segment: "Road Segmentation",
  health: "Health Dashboard",
  dedup: "Deduplication",
  export: "Export Builder",
  upload: "Upload Images",
  queue: "Annotation Queue",
  admin: "Assign Jobs",
  review: "QA Review",
  reviewFast: "Fast Review",
  roadAnalysis: "Road Condition Analysis",
  roadTaxonomy: "Road Taxonomy",
  agriAnalysis: "Agri Analysis",
  agriTaxonomy: "Agri Taxonomy",
  training: "Model Training",
  datasets: "Datasets",
  fleet: "Nodes",
  liveAnnotate: "Live Annotation",
  settings: "Settings",
};

/** Admin/QA-only routes — non-admins are redirected to dashboard. */
export const ADMIN_VIEWS: View[] = ["admin", "review", "reviewFast"];

/** Views requiring specific roles beyond feature flags. */
export const ROLE_GATED_VIEWS: View[] = [
  "admin",
  "review",
  "reviewFast",
  "roadAnalysis",
  "agriAnalysis",
  "dedup",
  "training",
  "export",
  "fleet",
];

export const SESSION_VIEWS: View[] = ["annotate", "agriAnnotate", "segment"];
