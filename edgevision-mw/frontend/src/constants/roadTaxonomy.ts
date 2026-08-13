import type { RoadClassInfo } from "../types";

export const ROAD_SURFACE_CLASSES: Record<number, RoadClassInfo> = {
  0: { id: 0, name: "good_road", color: "#4CAF50", description: "Smooth paved/asphalt surface in good condition" },
  1: { id: 1, name: "pothole", color: "#F44336", description: "Cavity or hole in the road surface" },
  2: { id: 2, name: "crack", color: "#FF9800", description: "Linear fracture (single or crocodile cracking)" },
  3: { id: 3, name: "dust_road", color: "#795548", description: "Unpaved dirt/dust surface" },
  4: { id: 4, name: "gravel_road", color: "#9E9E9E", description: "Unpaved surface with loose gravel/stones" },
  5: { id: 5, name: "road_marking", color: "#2196F3", description: "Painted lane lines, crosswalks, arrows" },
  6: { id: 6, name: "shoulder", color: "#8BC34A", description: "Road edge / verge (non-carriageway)" },
};

export const ROAD_TAXONOMY_VERSION = "v1.0";

export const ROAD_CLASS_ARRAY: RoadClassInfo[] = Object.values(ROAD_SURFACE_CLASSES);

export function getRoadClassColor(classId: number): string {
  return ROAD_SURFACE_CLASSES[classId]?.color ?? "#999999";
}

export function getRoadClassName(classId: number): string {
  return ROAD_SURFACE_CLASSES[classId]?.name ?? `class_${classId}`;
}

export const ROAD_CLASS_DISPLAY_NAMES: Record<string, { en: string; ny: string }> = {
  good_road: { en: "Good Road", ny: "Msewu Wabwino" },
  pothole: { en: "Pothole", ny: "Dzenje" },
  crack: { en: "Crack", ny: "Ming'alu" },
  dust_road: { en: "Dust Road", ny: "Msewu Wafumbi" },
  gravel_road: { en: "Gravel Road", ny: "Msewu Wamiyala" },
  road_marking: { en: "Road Marking", ny: "Chizindikiro Chamsewu" },
  shoulder: { en: "Shoulder", ny: "Mphepete" },
};
