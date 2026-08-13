import type { AgriClassInfo } from "../types";

export const AGRI_CROP_CLASSES: Record<number, AgriClassInfo> = {
  0: { id: 0, name: "maize", color: "#FDD835", description: "Maize / corn crop (Zea mays)" },
  1: { id: 1, name: "rice", color: "#81C784", description: "Paddy or upland rice (Oryza sativa)" },
  2: { id: 2, name: "cassava", color: "#A1887F", description: "Cassava / manioc (Manihot esculenta)" },
  3: { id: 3, name: "groundnuts", color: "#D7CCC8", description: "Groundnuts / peanuts (Arachis hypogaea)" },
  4: { id: 4, name: "cotton", color: "#FFFFFF", description: "Cotton (Gossypium spp.)" },
  5: { id: 5, name: "tobacco", color: "#A5D6A7", description: "Tobacco (Nicotiana tabacum)" },
  6: { id: 6, name: "sugarcane", color: "#66BB6A", description: "Sugarcane (Saccharum officinarum)" },
  7: { id: 7, name: "beans", color: "#8D6E63", description: "Common beans / legumes (Phaseolus vulgaris)" },
  8: { id: 8, name: "sweet_potato", color: "#F48FB1", description: "Sweet potato (Ipomoea batatas)" },
  9: { id: 9, name: "vegetables", color: "#4CAF50", description: "Leafy greens, tomatoes, onions, mixed vegetables" },
};

export const AGRI_HEALTH_CLASSES: Record<number, AgriClassInfo> = {
  0: { id: 0, name: "healthy", color: "#4CAF50", description: "Crop in good health, normal growth – no visible stress" },
  1: { id: 1, name: "stressed", color: "#FF9800", description: "Mild water/temperature stress – wilting or discoloration" },
  2: { id: 2, name: "diseased", color: "#F44336", description: "Fungal, bacterial, or viral infection present" },
  3: { id: 3, name: "pest_infested", color: "#E91E63", description: "Insect pest damage – leaf skeletonization, stunting" },
  4: { id: 4, name: "nutrient_deficient", color: "#FFEB3B", description: "Chlorosis or stunting from nitrogen/phosphorus deficiency" },
  5: { id: 5, name: "bare_soil", color: "#795548", description: "No crop cover – fallow, eroded, or pre-planting" },
  6: { id: 6, name: "weed_infestation", color: "#9C27B0", description: "Heavy weed competition reducing crop yield" },
  7: { id: 7, name: "water_logged", color: "#2196F3", description: "Flooded or saturated soil – root oxygen stress" },
  8: { id: 8, name: "drought_stressed", color: "#795548", description: "Severe moisture deficit – leaf rolling, browning" },
};

export const AGRI_TAXONOMY_VERSION = "v1.0";

export const AGRI_CROP_ARRAY: AgriClassInfo[] = Object.values(AGRI_CROP_CLASSES);
export const AGRI_HEALTH_ARRAY: AgriClassInfo[] = Object.values(AGRI_HEALTH_CLASSES);

export function getAgriCropColor(classId: number): string {
  return AGRI_CROP_CLASSES[classId]?.color ?? "#999999";
}

export function getAgriCropName(classId: number): string {
  return AGRI_CROP_CLASSES[classId]?.name ?? `crop_${classId}`;
}

export function getAgriHealthColor(classId: number): string {
  return AGRI_HEALTH_CLASSES[classId]?.color ?? "#999999";
}

export function getAgriHealthName(classId: number): string {
  return AGRI_HEALTH_CLASSES[classId]?.name ?? `health_${classId}`;
}

export const AGRI_CROP_DISPLAY_NAMES: Record<string, { en: string; ny: string }> = {
  maize: { en: "Maize", ny: "Chimanga" },
  rice: { en: "Rice", ny: "Mpunga" },
  cassava: { en: "Cassava", ny: "Chinangwa" },
  groundnuts: { en: "Groundnuts", ny: "Mtedza" },
  cotton: { en: "Cotton", ny: "Thonje" },
  tobacco: { en: "Tobacco", ny: "Fodya" },
  sugarcane: { en: "Sugarcane", ny: "Nzimbe" },
  beans: { en: "Beans", ny: "Nyemba" },
  sweet_potato: { en: "Sweet Potato", ny: "Mbatata" },
  vegetables: { en: "Vegetables", ny: "Masamba" },
};

export const AGRI_HEALTH_DISPLAY_NAMES: Record<string, { en: string; ny: string }> = {
  healthy: { en: "Healthy", ny: "Wathanzi" },
  stressed: { en: "Stressed", ny: "Wopanikizika" },
  diseased: { en: "Diseased", ny: "Matenda" },
  pest_infested: { en: "Pest Infested", ny: "Tizilombo" },
  nutrient_deficient: { en: "Nutrient Deficient", ny: "Kusowa Zakudya" },
  bare_soil: { en: "Bare Soil", ny: "Nthaka Yopanda" },
  weed_infestation: { en: "Weed Infestation", ny: "Nzeru" },
  water_logged: { en: "Water Logged", ny: "Madzi Ochuluka" },
  drought_stressed: { en: "Drought Stressed", ny: "Chilala" },
};
