from __future__ import annotations

import numpy as np


class TestLiveInferenceMasks:
    def test_bytetrack_preserves_mask_on_output(self):
        from app.ai.object_tracker import ByteTrack

        tracker = ByteTrack()
        mask = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]]
        detections = [
            {
                "bbox": [10.0, 20.0, 110.0, 120.0],
                "class_name": "person",
                "confidence": 0.9,
                "mask": mask,
                "mask_format": "polygon",
            }
        ]
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        tracked = tracker.update(detections, image=image)
        assert len(tracked) == 1
        assert tracked[0].get("mask") == mask
        assert tracked[0].get("mask_format") == "polygon"

    def test_attach_masks_from_instances_matches_pixel_xyxy(self):
        from app.ai.yolo_seg import attach_masks_from_instances

        mask = np.zeros((480, 640), dtype=bool)
        mask[50:150, 80:200] = True
        instances = [
            {
                "class_name": "car",
                "bbox": [80 / 640, 50 / 480, 120 / 640, 100 / 480],
                "confidence": 0.88,
                "mask": mask,
            }
        ]
        tracked = [
            {
                "track_id": 1,
                "bbox": [80.0, 50.0, 200.0, 150.0],
                "class_name": "car",
                "confidence": 0.88,
            }
        ]
        enriched = attach_masks_from_instances(tracked, instances, 640, 480)
        assert enriched[0].get("mask_format") == "polygon"
        assert len(enriched[0]["mask"]) >= 3

    def test_build_annotations_includes_mask_and_bbox_3d(self):
        from app.ai.live_inference import build_annotations

        tracked = [
            {
                "track_id": 1,
                "bbox": [50.0, 40.0, 150.0, 140.0],
                "class_name": "car",
                "confidence": 0.91,
                "mask": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3]],
                "mask_format": "polygon",
                "bbox_3d": {
                    "corners": [[0.1, 0.2, 0.5]] * 8,
                    "depth_available": np.bool_(True),
                },
            }
        ]
        anns = build_annotations(tracked)
        assert anns[0]["mask_format"] == "polygon"
        assert len(anns[0]["mask"]) == 3
        assert anns[0]["bbox_3d"]["depth_available"] is True
        assert len(anns[0]["bbox_3d"]["corners"]) == 8

    def test_seg_pipeline_attaches_3d_for_vehicle(self):
        from app.ai.live_inference import attach_depth_boxes, build_annotations

        tracked = [
            {
                "track_id": 2,
                "bbox": [100.0, 80.0, 260.0, 220.0],
                "class_name": "car",
                "confidence": 0.85,
            }
        ]
        image = np.zeros((384, 512, 3), dtype=np.uint8)
        enriched = attach_depth_boxes(tracked, image, depth_map=None, depth_available=False)
        anns = build_annotations(enriched)
        assert anns[0].get("bbox_3d") is not None
        assert len(anns[0]["bbox_3d"]["corners"]) == 8
