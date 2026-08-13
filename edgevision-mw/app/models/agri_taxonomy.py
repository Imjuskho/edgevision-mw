from __future__ import annotations

from typing import TypedDict


class AgriClassDef(TypedDict):
    name: str
    color: str
    description: str


CROP_CLASSES: dict[int, AgriClassDef] = {
    0: {"name": "maize", "color": "#FDD835", "description": "Maize / corn crop (Zea mays)"},
    1: {"name": "rice", "color": "#81C784", "description": "Paddy or upland rice (Oryza sativa)"},
    2: {"name": "cassava", "color": "#A1887F", "description": "Cassava / manioc (Manihot esculenta)"},
    3: {"name": "groundnuts", "color": "#D7CCC8", "description": "Groundnuts / peanuts (Arachis hypogaea)"},
    4: {"name": "cotton", "color": "#FFFFFF", "description": "Cotton (Gossypium spp.)"},
    5: {"name": "tobacco", "color": "#A5D6A7", "description": "Tobacco (Nicotiana tabacum)"},
    6: {"name": "sugarcane", "color": "#66BB6A", "description": "Sugarcane (Saccharum officinarum)"},
    7: {"name": "beans", "color": "#8D6E63", "description": "Common beans / legumes (Phaseolus vulgaris)"},
    8: {"name": "sweet_potato", "color": "#F48FB1", "description": "Sweet potato (Ipomoea batatas)"},
    9: {"name": "vegetables", "color": "#4CAF50", "description": "Leafy greens, tomatoes, onions, mixed vegetables"},
}

HEALTH_CLASSES: dict[int, AgriClassDef] = {
    0: {"name": "healthy", "color": "#4CAF50", "description": "Crop in good health, normal growth - no visible stress"},
    1: {"name": "stressed", "color": "#FF9800", "description": "Mild water/temperature stress - wilting or discoloration"},
    2: {"name": "diseased", "color": "#F44336", "description": "Fungal, bacterial, or viral infection present"},
    3: {"name": "pest_infested", "color": "#E91E63", "description": "Insect pest damage - leaf skeletonization, stunting"},
    4: {"name": "nutrient_deficient", "color": "#FFEB3B", "description": "Chlorosis or stunting from nitrogen/phosphorus deficiency"},
    5: {"name": "bare_soil", "color": "#795548", "description": "No crop cover - fallow, eroded, or pre-planting"},
    6: {"name": "weed_infestation", "color": "#9C27B0", "description": "Heavy weed competition reducing crop yield"},
    7: {"name": "water_logged", "color": "#2196F3", "description": "Flooded or saturated soil - root oxygen stress"},
    8: {"name": "drought_stressed", "color": "#795548", "description": "Severe moisture deficit - leaf rolling, browning"},
}

AGRI_TAXONOMY_VERSION = "v1.0"

CROP_TYPES = [c["name"] for c in CROP_CLASSES.values()]
HEALTH_STATUS_TYPES = [c["name"] for c in HEALTH_CLASSES.values()]


def get_crop_class(class_id: int) -> AgriClassDef | None:
    return CROP_CLASSES.get(class_id)


def get_health_class(class_id: int) -> AgriClassDef | None:
    return HEALTH_CLASSES.get(class_id)


def get_crop_class_by_name(name: str) -> tuple[int, AgriClassDef] | None:
    for cid, cdef in CROP_CLASSES.items():
        if cdef["name"] == name:
            return cid, cdef
    return None


def get_health_class_by_name(name: str) -> tuple[int, AgriClassDef] | None:
    for cid, cdef in HEALTH_CLASSES.items():
        if cdef["name"] == name:
            return cid, cdef
    return None
