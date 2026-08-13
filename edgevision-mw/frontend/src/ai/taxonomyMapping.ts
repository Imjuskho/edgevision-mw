import { TAXONOMY_CATEGORIES, type LabelCategory } from "../constants/taxonomy";
import { AGRI_CROP_CLASSES, AGRI_HEALTH_CLASSES } from "../constants/agriTaxonomy";

type TaxonomyContext = "road" | "agri";

const ROAD_YOLO_TO_TAXONOMY: Record<string, string> = {
  car: "car_private",
  matola: "minibus",
  pedestrian: "pedestrian_roadside",
  bicycle: "bicycle_private",
  motorcycle: "motorcycle_kabaza",
  goat: "goat_sheep",
  cow: "cattle",
  dog: "dog",
  bus: "bus",
  minibus: "minibus",
};

const ROAD_TAXONOMY_TO_YOLO: Record<string, string> = {};
for (const [yolo, tax] of Object.entries(ROAD_YOLO_TO_TAXONOMY)) {
  ROAD_TAXONOMY_TO_YOLO[tax] = yolo;
}

const ROAD_AMBIGUOUS_CLASSES: Record<string, string[]> = {
  car: ["car_private", "taxi", "pickup_passenger", "gov_ngo_vehicle"],
  bus: ["bus", "gov_ngo_vehicle"],
  minibus: ["minibus", "taxi"],
  pedestrian: ["pedestrian_roadside", "pedestrian_carriageway", "pedestrian_head_load", "pedestrian_child_wrap"],
  bicycle: ["bicycle_private", "bicycle_kabaza", "bicycle_cargo"],
  motorcycle: ["motorcycle_kabaza", "motorcycle_private"],
  goat: ["goat_sheep"],
  cow: ["cattle", "draft_animal_harness"],
  dog: ["dog"],
  matola: ["minibus"],
};

function normalizeLabel(label: string): string {
  return label.toLowerCase().replace(/[\s_-]+/g, "_").trim();
}

export function yoloClassToTaxonomy(yoloClass: string, context: TaxonomyContext = "road"): string {
  const key = normalizeLabel(yoloClass);
  if (context === "road") {
    return ROAD_YOLO_TO_TAXONOMY[key] || "car_private";
  }
  return "car_private";
}

export function taxonomyToYoloClass(taxonomyLabel: string, context: TaxonomyContext = "road"): string | null {
  const key = normalizeLabel(taxonomyLabel);
  if (context === "road") {
    return ROAD_TAXONOMY_TO_YOLO[key] || null;
  }
  return null;
}

export function getAmbiguousMappings(yoloClass: string, context: TaxonomyContext = "road"): string[] {
  const key = normalizeLabel(yoloClass);
  if (context === "road") {
    return ROAD_AMBIGUOUS_CLASSES[key] || [ROAD_YOLO_TO_TAXONOMY[key]].filter(Boolean);
  }
  return [yoloClassToTaxonomy(yoloClass, context)];
}

export function getTaxonomyCategory(label: string, context: TaxonomyContext = "road"): LabelCategory | undefined {
  if (context === "road") {
    return TAXONOMY_CATEGORIES.find((cat) =>
      cat.classes.some((c) => c.label === label || normalizeLabel(c.label) === normalizeLabel(label))
    );
  }
  return undefined;
}

export function getAgriLabelFromPrediction(classId: number, isHealth: boolean): string {
  if (isHealth) {
    return AGRI_HEALTH_CLASSES[classId]?.name || "unknown";
  }
  return AGRI_CROP_CLASSES[classId]?.name || "unknown";
}

export function YOLO_CLASS_NAMES(context: TaxonomyContext = "road"): string[] {
  if (context === "road") return Object.keys(ROAD_YOLO_TO_TAXONOMY);
  return Object.keys(ROAD_YOLO_TO_TAXONOMY);
}

export function confidenceToQuality(confidence: number): number {
  if (confidence >= 0.9) return 0.95;
  if (confidence >= 0.7) return 0.85;
  if (confidence >= 0.5) return 0.7;
  return 0.5;
}

const AGRI_CLASS_NAMES = Object.values(AGRI_CROP_CLASSES).map((c) => c.name);
const AGRI_HEALTH_NAMES = Object.values(AGRI_HEALTH_CLASSES).map((c) => c.name);

export function getAgriClassNames(): string[] {
  return AGRI_CLASS_NAMES;
}

export function getAgriHealthNames(): string[] {
  return AGRI_HEALTH_NAMES;
}

export function classifyAgriByColor(
  imageData: ImageData
): { cropType: string; healthStatus: string; confidence: number } {
  const { data, width, height } = imageData;
  let greenSum = 0;
  let greenPixels = 0;
  let brownPixels = 0;
  let yellowPixels = 0;
  let darkPixels = 0;

  for (let y = 0; y < height; y += 4) {
    for (let x = 0; x < width; x += 4) {
      const idx = (y * width + x) * 4;
      const r = data[idx];
      const g = data[idx + 1];
      const b = data[idx + 2];

      const total = r + g + b;
      if (total < 60) { darkPixels++; continue; }

      const greenRatio = g / (total || 1);
      const redRatio = r / (total || 1);

      if (greenRatio > 0.4 && g > 100) {
        greenSum += greenRatio;
        greenPixels++;
      }
      if (redRatio > 0.5 && r > 120 && g < 100) {
        brownPixels++;
      }
      if (g > 150 && r > 150 && b < 100) {
        yellowPixels++;
      }
    }
  }

  const sampledPixels = greenPixels + brownPixels + yellowPixels + darkPixels || 1;
  const greenDensity = greenPixels / sampledPixels;
  const brownDensity = brownPixels / sampledPixels;
  const yellowDensity = yellowPixels / sampledPixels;
  const darkDensity = darkPixels / sampledPixels;

  let cropType = "unknown";
  let healthStatus = "healthy";
  let confidence = 0.5;

  if (greenDensity > 0.35) {
    cropType = "vegetables";
    healthStatus = "healthy";
    confidence = 0.5 + greenDensity * 0.3;
  } else if (yellowDensity > 0.25) {
    cropType = "maize";
    healthStatus = greenDensity > 0.2 ? "stressed" : "nutrient_deficient";
    confidence = 0.5 + yellowDensity * 0.2;
  } else if (brownDensity > 0.4) {
    cropType = "cassava";
    healthStatus = brownDensity > 0.6 ? "drought_stressed" : "stressed";
    confidence = 0.5 + brownDensity * 0.2;
  } else if (darkDensity > 0.6) {
    cropType = "groundnuts";
    healthStatus = "water_logged";
    confidence = 0.4;
  } else {
    const avgGreen = greenPixels > 0 ? greenSum / greenPixels : 0;
    if (avgGreen > 0.35) {
      cropType = "sweet_potato";
      healthStatus = "healthy";
      confidence = 0.45;
    } else {
      cropType = "groundnuts";
      healthStatus = "stressed";
      confidence = 0.35;
    }
  }

  if (yellowDensity > 0.3) {
    healthStatus = "nutrient_deficient";
  } else if (brownDensity > 0.5 && greenDensity < 0.15) {
    healthStatus = "drought_stressed";
  } else if (darkDensity > 0.5) {
    healthStatus = "water_logged";
  } else if (greenDensity > 0.4) {
    healthStatus = "healthy";
  }

  return { cropType, healthStatus, confidence: Math.min(0.95, Math.max(0.3, confidence)) };
}
