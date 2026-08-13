const LAST_DATASET_KEY = "studio_last_dataset";

/** Persist the last selected dataset so sidebar navigation works across sessions. */
export function getLastDatasetId(): string {
  try {
    return localStorage.getItem(LAST_DATASET_KEY) || "";
  } catch {
    return "";
  }
}

export function setLastDatasetId(datasetId: string): void {
  try {
    if (datasetId) {
      localStorage.setItem(LAST_DATASET_KEY, datasetId);
    } else {
      localStorage.removeItem(LAST_DATASET_KEY);
    }
  } catch {
    // ignore storage failures (private mode, quota, etc.)
  }
}

export function clearLastDatasetId(): void {
  setLastDatasetId("");
}

/** URL dataset wins; fall back to last sidebar selection. */
export function resolveDatasetId(urlDatasetId?: string): string {
  return urlDatasetId || getLastDatasetId() || "";
}
