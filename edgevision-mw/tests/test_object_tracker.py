from __future__ import annotations

import numpy as np
import pytest

from app.ai.object_tracker import ByteTrack, iou


def _det(bbox, class_name="car", confidence=0.9):
    return {"bbox": list(bbox), "class_name": class_name, "confidence": confidence}


class TestObjectTracker:
    def test_track_id_continuity_over_frames(self):
        """A moving object should keep the same track_id for multiple frames."""
        tracker = ByteTrack(model_type="object_detection")
        track_id = None

        for i in range(12):
            x = 10 + i * 5
            dets = [_det([x, 10, x + 40, 50], "car", 0.85)]
            result = tracker.update(dets)
            assert len(result) == 1
            if track_id is None:
                track_id = result[0]["track_id"]
            else:
                assert result[0]["track_id"] == track_id

    def test_class_mismatch_rejects_wrong_class(self):
        tracker = ByteTrack(model_type="object_detection")
        tracker.update([_det([10, 10, 50, 50], "car", 0.9)])

        for _ in range(3):
            result = tracker.update([_det([12, 12, 52, 52], "person", 0.9)])
            assert result[0]["class_name"] == "car"

    def test_coasting_keeps_track_alive(self):
        tracker = ByteTrack(model_type="object_detection")
        tracker.update([_det([10, 10, 50, 50], "car", 0.9)])
        tracker.update([_det([15, 10, 55, 50], "car", 0.9)])
        tracker.update([_det([20, 10, 60, 50], "car", 0.9)])

        tid = tracker.update([_det([25, 10, 65, 50], "car", 0.9)])[0]["track_id"]

        for _ in range(5):
            empty = tracker.update([])
            assert any(t["track_id"] == tid for t in empty)

    def test_reset_clears_tracks(self):
        tracker = ByteTrack(model_type="object_detection")
        tracker.update([_det([10, 10, 50, 50], "car", 0.9)])
        tracker.reset()
        result = tracker.update([_det([10, 10, 50, 50], "car", 0.9)])
        assert result[0]["track_id"] == 1

    def test_iou_calculation(self):
        a = np.array([0, 0, 10, 10])
        b = np.array([5, 5, 15, 15])
        assert iou(a, b) == pytest.approx(25 / 175, rel=0.01)

    def test_kalman_predicts_motion(self):
        tracker = ByteTrack(model_type="object_detection")
        for i in range(10):
            x = 10 + i * 8
            tracker.update([_det([x, 10, x + 40, 50], "car", 0.9)])

        # One missed frame — coasting should keep track
        coasted = tracker.update([])
        assert len(coasted) >= 1

    def test_stable_id_for_5_seconds_at_2fps(self):
        """Simulate 10 frames (5 s at 2 fps) with gradual movement."""
        tracker = ByteTrack(model_type="object_detection")
        track_id = None
        for frame in range(10):
            x = 20 + frame * 3
            out = tracker.update([_det([x, 100, x + 60, 160], "person", 0.88)])
            assert len(out) == 1
            if track_id is None:
                track_id = out[0]["track_id"]
            assert out[0]["track_id"] == track_id
