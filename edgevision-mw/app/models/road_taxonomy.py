from __future__ import annotations

from typing import TypedDict


class RoadClassDef(TypedDict):
    name: str
    color: str
    description: str


ROAD_SURFACE_CLASSES: dict[int, RoadClassDef] = {
    0: {"name": "good_road", "color": "#4CAF50", "description": "Smooth paved/asphalt surface in good condition"},
    1: {"name": "pothole", "color": "#F44336", "description": "Cavity or hole in the road surface"},
    2: {"name": "crack", "color": "#FF9800", "description": "Linear fracture (single or crocodile cracking)"},
    3: {"name": "dust_road", "color": "#795548", "description": "Unpaved dirt/dust surface"},
    4: {"name": "gravel_road", "color": "#9E9E9E", "description": "Unpaved surface with loose gravel/stones"},
    5: {"name": "road_marking", "color": "#2196F3", "description": "Painted lane lines, crosswalks, arrows"},
    6: {"name": "shoulder", "color": "#8BC34A", "description": "Road edge / verge (non-carriageway)"},
}

ROAD_TAXONOMY_VERSION = "v1.0"

ROAD_SURFACE_TYPES = ["paved", "unpaved", "mixed"]


def get_road_class(class_id: int) -> RoadClassDef | None:
    return ROAD_SURFACE_CLASSES.get(class_id)


def get_road_class_by_name(name: str) -> tuple[int, RoadClassDef] | None:
    for cid, cdef in ROAD_SURFACE_CLASSES.items():
        if cdef["name"] == name:
            return cid, cdef
    return None
