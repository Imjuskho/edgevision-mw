import { ALL_LABELS } from "../constants/taxonomy";
import { AGRI_CROP_DISPLAY_NAMES, AGRI_HEALTH_DISPLAY_NAMES } from "../constants/agriTaxonomy";

export interface AnnotateLabelOption {
  label: string;
  name: string;
  color: string;
  shortcut?: number;
}

export function getAllLabelsForContext(ctx: "road" | "agri"): AnnotateLabelOption[] {
  if (ctx === "agri") {
    return [
      ...Object.entries(AGRI_CROP_DISPLAY_NAMES).map(([k, v]) => ({
        label: k,
        name: v.en,
        color: "#22c55e",
      })),
      ...Object.entries(AGRI_HEALTH_DISPLAY_NAMES).map(([k, v]) => ({
        label: k,
        name: v.en,
        color: "#f97316",
      })),
    ].slice(0, 9).map((item, i) => ({ ...item, shortcut: i + 1 }));
  }

  const flat = ALL_LABELS.slice(0, 9);
  return flat.map((l, i) => ({
    label: l.label,
    name: l.name,
    color: l.color,
    shortcut: i + 1,
  }));
}

export function slugifyDatasetId(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return slug || `dataset-${Date.now()}`;
}
