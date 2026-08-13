from __future__ import annotations

import json
from uuid import uuid4

from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus
from app.services.export_builder import (
    _build_coco_json,
    _build_pascal_voc_xml,
    _build_yolo_txt,
    _preview_for_format,
)


def _make_ann(**kwargs) -> Annotation:
    defaults = dict(
        batch_id=uuid4(),
        image_index=0,
        image_path="exports/sample.jpg",
        thumbnail_path="exports/sample.jpg",
        detected_objects={
            "objects": [
                {
                    "class_name": "car",
                    "bbox": [10, 20, 50, 40],
                    "mask": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]],
                    "bbox_3d": {"yaw": 0.1, "depth_available": True},
                }
            ],
            "orientation": "mirrored",
        },
        auto_labels={},
        status=AnnotationStatus.CERTIFIED,
        quality_score=0.9,
    )
    defaults.update(kwargs)
    return Annotation(**defaults)


def test_preview_for_format_coco_badges():
    ann = _make_ann()
    preview = _preview_for_format(ann, "COCO")
    assert preview["format"] == "COCO"
    assert "segmentation" in preview["badges"]
    assert "bbox_3d" in preview["badges"]
    assert preview["orientation_mode"] == "mirrored"


def test_build_coco_includes_segmentation_and_attributes():
    ann = _make_ann()
    content = _build_coco_json([ann])
    data = json.loads(content)
    assert data["images"][0]["orientation_mode"] == "mirrored"
    assert "segmentation" in data["annotations"][0]
    assert "attributes" in data["annotations"][0]


def test_build_yolo_seg_companion_comment():
    ann = _make_ann()
    txt = _build_yolo_txt([ann])
    assert "# seg" in txt
    assert "orientation=mirrored" in txt


def test_build_pascal_voc_metadata():
    ann = _make_ann()
    xml = _build_pascal_voc_xml([ann])
    assert "<orientation_mode>mirrored</orientation_mode>" in xml
    assert "<segmentation>" in xml
    assert "<attributes>" in xml
