from __future__ import annotations

import json
from uuid import uuid4

from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus
from app.services.export_builder import (
    _build_cityscapes_json,
    _build_coco_json,
    _build_kitti_txt,
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


def _ann_with_3d():
    return _make_ann(
        image_path="exports/sample_3d.jpg",
        detected_objects={
            "objects": [
                {
                    "class_name": "car",
                    "bbox": [100, 200, 300, 150],
                    "bbox_3d": {
                        "dimensions": [4.5, 1.8, 1.5],
                        "yaw": 0.2,
                        "corners": [[0.0, 0.0, 5.0]] * 8,
                        "depth_available": True,
                    },
                }
            ],
            "orientation": "normal",
        }
    )


def test_build_kitti_label_stream():
    ann = _make_ann()
    txt = _build_kitti_txt([ann])
    assert "# sample.jpg orientation=mirrored" in txt
    line = [l for l in txt.splitlines() if l and not l.startswith("#")][0]
    parts = line.split()
    assert parts[0] == "car"
    assert parts[1] == "-1"  # truncated
    assert parts[2] == "-1"  # occluded
    assert parts[4:8] == ["10.0000", "20.0000", "60.0000", "60.0000"]


def test_build_kitti_fills_3d_fields():
    ann = _ann_with_3d()
    txt = _build_kitti_txt([ann])
    line = [l for l in txt.splitlines() if l and not l.startswith("#")][0]
    parts = line.split()
    # h w l from bbox_3d dimensions [length, width, height]
    assert parts[8] == "1.5000"
    assert parts[9] == "1.8000"
    assert parts[10] == "4.5000"
    assert parts[11] == "0.0000"  # location x (corner centroid)
    assert parts[13] == "5.0000"  # location z
    assert parts[14] == "0.2000"  # rotation_y = yaw


def test_build_cityscapes_polygons():
    ann = _make_ann()
    content = _build_cityscapes_json([ann])
    bundle = json.loads(content)
    assert "sample.jpg" in bundle
    entry = bundle["sample.jpg"]
    assert entry["imgWidth"] == 1920
    assert entry["imgHeight"] == 1080
    assert entry["orientation_mode"] == "mirrored"
    obj = entry["objects"][0]
    assert obj["label"] == "car"
    assert obj["instanceId"] == 1
    assert obj["polygon"][0] == [192.0, 108.0]  # normalized -> pixels


def test_build_cityscapes_instance_ids_increment():
    ann = _ann_with_3d()
    content = _build_cityscapes_json([ann, _make_ann()])
    bundle = json.loads(content)
    ids = [o["instanceId"] for e in bundle.values() for o in e["objects"]]
    assert ids == [1, 2]


def test_build_cityscapes_uses_recorded_image_dims():
    ann = _make_ann()
    ann.detected_objects = {
        "objects": [
            {
                "class_name": "car",
                "bbox": [0.1, 0.1, 0.4, 0.4],
                "mask": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]],
            }
        ],
        "image_width": 640,
        "image_height": 480,
    }
    content = _build_cityscapes_json([ann])
    entry = json.loads(content)["sample.jpg"]
    assert entry["imgWidth"] == 640.0
    assert entry["imgHeight"] == 480.0
    assert entry["objects"][0]["polygon"][0] == [64.0, 48.0]

    preview = _preview_for_format(ann, "CITYSCAPES")
    assert preview["imgWidth"] == 640.0


def test_preview_routes_kitti_and_cityscapes():
    ann = _make_ann()
    k = _preview_for_format(ann, "KITTI")
    assert k["format"] == "KITTI"
    assert k["lines"][0].startswith("car ")
    c = _preview_for_format(ann, "CITYSCAPES")
    assert c["format"] == "CITYSCAPES"
    assert c["objects"][0]["label"] == "car"
